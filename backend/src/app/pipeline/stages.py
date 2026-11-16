"""The pipeline: landing zone to governed tables, with the three-way match.

  land      read and hash every raw file (bronze)
  parse     invoice text to typed fields; a document that will not parse is held
  conform   resolve the supplier, normalise the invoice number, convert to AUD (silver)
  units     bring invoice lines to the order's unit of measure (drums to metres)
  match     join each line to its order line and what was received
  checks    ten checks in a fixed order; the first to fail holds the invoice
  publish   star-schema tables and a digest of every partition (gold)

Hold, never guess: a check that cannot decide holds the invoice and records
why. Nothing is dropped - every document that arrives is in fact_invoice, and
every held one has an exception row with its reason and the money at risk.

Each control can be switched off, which is how the ablation prices it.
"""

from __future__ import annotations

import csv
import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from src.app.pipeline import reference as ref
from src.app.pipeline.parse import ParseError, normalise_number, parse_invoice

CHECK_ORDER = ["unreadable", "bank_details", "duplicate", "po_reference", "currency", "arithmetic", "tax", "price",
               "quantity", "unplanned_charge"]
CONTROLS = ["uom_normalise", "charge_tolerance", "bank_details", "duplicate", "po_reference", "currency", "arithmetic",
            "tax", "price", "quantity", "unplanned_charge"]
ALL_ON = {c: True for c in CONTROLS}


@dataclass
class Stage:
    name: str
    rows_in: int
    rows_out: int
    held: int
    wall_ms: float
    note: str = ""


@dataclass
class PipelineResult:
    files: pd.DataFrame
    tables: dict[str, pd.DataFrame]
    partition_hashes: pd.DataFrame
    stages: list[Stage]
    # Plain structures the case builder and the ablation read.
    docs: list[dict] = field(default_factory=list)
    pos: dict[str, dict] = field(default_factory=dict)
    suppliers: dict[str, dict] = field(default_factory=dict)
    items: dict[str, dict] = field(default_factory=dict)
    notices: list[dict] = field(default_factory=list)


def _read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frame_digest(df: pd.DataFrame) -> str:
    body = df.to_csv(index=False, float_format="%.4f", lineterminator="\n")
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def mask_account(bsb: str, account: str) -> str:
    return f"{bsb[:2]}x-xxx / *****{account[-3:]}"


def fx_rate(currency: str, month: str) -> float:
    return ref.FX_E4[currency][month] / 10000


def run_pipeline(raw: Path, controls: dict[str, bool] | None = None,
                 approved_notices: frozenset[str] | set[str] = frozenset(), hash_files: bool = True) -> PipelineResult:
    on = {**ALL_ON, **(controls or {})}
    pol = ref.POLICY
    stages: list[Stage] = []
    clock = time.perf_counter()

    def stage(name: str, rows_in: int, rows_out: int, held: int = 0, note: str = "") -> None:
        nonlocal clock
        now = time.perf_counter()
        stages.append(Stage(name, rows_in, rows_out, held, round((now - clock) * 1000, 1), note))
        clock = now

    # ---- land -------------------------------------------------------------------
    file_rows = []
    erp = {p.stem: _read_csv(p) for p in sorted((raw / "erp").glob("*.csv"))}
    for p in sorted((raw / "erp").glob("*.csv")):
        file_rows.append({"file": f"erp/{p.name}", "layer": "bronze", "rows": len(erp[p.stem]), "bytes": p.stat().st_size,
                          "sha256": _sha(p) if hash_files else ""})
    inbox: list[dict] = []
    for p in sorted((raw / "ap_inbox").glob("*.jsonl")):
        recs = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line]
        for i, r in enumerate(recs):
            r["file"], r["raw_row"] = f"ap_inbox/{p.name}", i + 1
        inbox += recs
        file_rows.append({"file": f"ap_inbox/{p.name}", "layer": "bronze", "rows": len(recs), "bytes": p.stat().st_size,
                          "sha256": _sha(p) if hash_files else ""})
    files = pd.DataFrame(file_rows)
    stage("land", int(files["rows"].sum()), int(files["rows"].sum()), note=f"{len(files)} files hashed on landing")

    suppliers = {s["supplier_id"]: s for s in erp["suppliers"]}
    by_name = {s["name"]: s for s in erp["suppliers"]}
    items = {i["item_id"]: {**i, "pack_size": int(i["pack_size"])} for i in erp["items"]}
    notices = [{**n, "uplift_pct": float(n["uplift_pct"]), "effective_from": date.fromisoformat(n["effective_from"])}
               for n in erp["supplier_notices"]]
    pos: dict[str, dict] = {}
    for h in erp["purchase_orders"]:
        pos[h["po_number"]] = {**h, "order_date": date.fromisoformat(h["order_date"]), "lines": {}, "invoices": []}
    for ln in erp["po_lines"]:
        pos[ln["po_number"]]["lines"][ln["item_id"]] = {
            "line_no": int(ln["line_no"]), "item_id": ln["item_id"], "qty": float(ln["qty"]), "uom": ln["uom"],
            "unit_price": float(ln["unit_price"]), "received": 0.0, "complete": None, "last_receipt": None, "dockets": []}
    by_line = {(po, ln["line_no"]): ln for po, p in pos.items() for ln in p["lines"].values()}
    for g in erp["goods_receipts"]:
        ln = by_line[(g["po_number"], int(g["line_no"]))]
        ln["received"] += float(g["qty_received"])
        ln["complete"] = g["delivery_complete"] == "Y"
        ln["last_receipt"] = g["received_date"]
        ln["dockets"].append(g["docket"])
    pos_by_supplier: dict[str, list[dict]] = {}
    for p in pos.values():
        pos_by_supplier.setdefault(p["supplier_id"], []).append(p)

    # ---- parse ------------------------------------------------------------------
    docs: list[dict] = []
    for r in sorted(inbox, key=lambda r: (r["received_at"], r["doc_id"])):
        d = {"doc_id": r["doc_id"], "received_at": datetime.fromisoformat(r["received_at"]), "month": r["received_at"][:7],
             "channel": r["channel"], "sender": r["sender"], "file": r["file"], "raw_row": r["raw_row"], "text": r["text"],
             "parsed": None, "supplier": None, "fails": {}, "flags": [], "po": None, "candidates": []}
        try:
            d["parsed"] = parse_invoice(r["text"])
        except ParseError as exc:
            d["fails"]["unreadable"] = (f"The document could not be read: {exc}.", 0.0)
        docs.append(d)
    unread = sum(1 for d in docs if d["parsed"] is None)
    stage("parse", len(docs), len(docs) - unread, unread, "three layouts; a document that will not parse is held, not guessed")

    # ---- conform ----------------------------------------------------------------
    for d in docs:
        p = d["parsed"]
        if p is None:
            continue
        d["supplier"] = by_name.get(p["supplier_name"])
        if d["supplier"] is None:
            d["fails"]["unreadable"] = (f"Supplier '{p['supplier_name']}' is not in the supplier master.", 0.0)
            continue
        d["norm_number"] = normalise_number(p["invoice_number"])
        d["fx"] = fx_rate(p["currency"], d["month"]) if p["currency"] in ref.FX_E4 else 1.0
        d["total_aud"] = round(p["total"] * d["fx"], 2)
        d["po"] = pos.get(p["po_number"]) if p["po_number"] else None
        if d["po"] is not None and d["po"]["supplier_id"] == d["supplier"]["supplier_id"]:
            d["po"]["invoices"].append(d)
    ok = [d for d in docs if d["supplier"] is not None]
    stage("conform", len(docs) - unread, len(ok), len(docs) - unread - len(ok), "supplier resolved, number normalised, converted to AUD at the month's rate")

    # ---- units ------------------------------------------------------------------
    converted = 0
    for d in ok:
        uplift = 0.0
        for n in notices:
            if n["notice_id"] in approved_notices and n["supplier_id"] == d["supplier"]["supplier_id"] \
                    and d["parsed"]["invoice_date"] >= n["effective_from"]:
                uplift = n["uplift_pct"] / 100
        for ln in d["parsed"]["lines"]:
            po_ln = d["po"]["lines"].get(ln["item_id"]) if d["po"] else None
            ln["po_line"] = po_ln
            ln["qty_m"], ln["price_m"] = ln["qty"], ln["unit_price"]
            item = items.get(ln["item_id"])
            if on["uom_normalise"] and po_ln and item and ln["uom"] != po_ln["uom"] and ln["uom"] == item["pack_uom"]:
                ln["qty_m"], ln["price_m"] = ln["qty"] * item["pack_size"], ln["unit_price"] / item["pack_size"]
                if "uom_converted" not in d["flags"]:
                    d["flags"].append("uom_converted")
                    converted += 1
            ln["expected"] = round(po_ln["unit_price"] * (1 + uplift), 6) if po_ln else None
    stage("units", len(ok), len(ok), 0, f"{converted} invoices billed in drums, reels or boxes brought to the order's unit")

    # ---- match and checks ---------------------------------------------------------
    seen_number: dict[tuple[str, str], dict] = {}
    seen_order_total: dict[tuple[str, str, float], list[dict]] = {}
    for d in ok:
        p, s, fails, fx = d["parsed"], d["supplier"], d["fails"], d["fx"]
        sid = s["supplier_id"]

        if on["bank_details"] and (p["bsb"], p["account"]) != (s["bsb"], s["account"]):
            fails["bank_details"] = ("The remittance account on the invoice is not the account on the supplier master "
                                     f"(last verified {date.fromisoformat(s['bank_verified_on']):%d/%m/%Y}).", d["total_aud"])

        first = seen_number.get((sid, d["norm_number"]))
        same = [o for o in seen_order_total.get((sid, p["po_number"] or "", p["total"]), [])
                if o["norm_number"] != d["norm_number"]
                and (d["received_at"] - o["received_at"]).days <= pol["duplicate_window_days"]] if p["po_number"] else []
        d["dup_of"], d["dup_like"] = first, same
        if on["duplicate"] and first is not None:
            fails["duplicate"] = (f"Same supplier and invoice number as {first['doc_id']} ({first['parsed']['invoice_number']}), "
                                  f"received {first['received_at']:%d/%m/%Y}.", d["total_aud"])
        elif on["duplicate"] and same:
            fails["duplicate"] = (f"Same supplier, order {p['po_number']} and total {p['total']:,.2f} as {same[0]['doc_id']} "
                                  f"({same[0]['parsed']['invoice_number']}), under a different number.", d["total_aud"])
        seen_number.setdefault((sid, d["norm_number"]), d)
        seen_order_total.setdefault((sid, p["po_number"] or "", p["total"]), []).append(d)

        po = d["po"]
        po_ok = po is not None and po["supplier_id"] == sid and all(ln["po_line"] for ln in p["lines"])
        if not po_ok:
            want = sorted((ln["item_id"], ln["qty_m"], round(ln["price_m"], 4)) for ln in p["lines"])
            for cand in pos_by_supplier.get(sid, []):
                have = sorted((ln["item_id"], ln["qty"], round(ln["unit_price"], 4)) for ln in cand["lines"].values())
                # A candidate is an order that could be this invoice's: same lines,
                # goods received, and nobody has invoiced it yet.
                if have == want and not cand["invoices"] and all(ln["received"] >= ln["qty"] for ln in cand["lines"].values()):
                    d["candidates"].append(cand)
            if on["po_reference"]:
                if not p["po_number"]:
                    why = "The invoice quotes no purchase order."
                elif po is None:
                    why = f"Purchase order {p['po_number']} does not exist."
                elif po["supplier_id"] != sid:
                    why = f"Purchase order {p['po_number']} belongs to another supplier."
                else:
                    why = f"A line on the invoice is not on purchase order {p['po_number']}."
                if d["candidates"]:
                    why += f" {len(d['candidates'])} received, uninvoiced order(s) from this supplier match the lines exactly: " \
                           f"{', '.join(c['po_number'] for c in d['candidates'][:3])}."
                fails["po_reference"] = (why, d["total_aud"])

        if on["currency"] and po_ok and p["currency"] != po["currency"]:
            gap = abs(p["total"] * fx - p["total"] * fx_rate(po["currency"], d["month"]))
            fails["currency"] = (f"Billed in {p['currency']}; the order is in {po['currency']}.", round(gap, 2))

        line_sum = round(sum(ln["amount"] for ln in p["lines"]), 2)
        built = round(p["subtotal"] + p["charge"] + p["tax"], 2)
        if on["arithmetic"] and (abs(line_sum - p["subtotal"]) > pol["arithmetic_tolerance"]
                                 or abs(built - p["total"]) > pol["arithmetic_tolerance"]):
            fails["arithmetic"] = (f"Subtotal, charges and tax come to {built:,.2f}; the invoice total says {p['total']:,.2f}.",
                                   round(max(p["total"] - built, 0) * fx, 2))

        rate = ref.TAX_RATE_BP[s["tax_code"]] / 10000
        expected_tax = round((p["subtotal"] + p["charge"]) * rate, 2)
        if on["tax"] and abs(p["tax"] - expected_tax) > pol["tax_tolerance"]:
            fails["tax"] = (f"Tax of {p['tax']:,.2f} charged; the supplier's tax code ({s['tax_code']}) implies {expected_tax:,.2f}.",
                            round(max(p["tax"] - expected_tax, 0) * fx, 2))

        if po_ok:
            over, short, risk_p, risk_q = [], [], 0.0, 0.0
            for ln in p["lines"]:
                po_ln = ln["po_line"]
                diff = (ln["price_m"] - ln["expected"]) * ln["qty_m"] * fx
                if ln["price_m"] > ln["expected"] * (1 + pol["price_tolerance_pct"]) and diff > pol["price_tolerance_line_aud"]:
                    over.append(f"line {ln['line_no']} {ln['item_id']} at {ln['price_m']:,.4f} against {ln['expected']:,.4f} "
                                f"({(ln['price_m'] / ln['expected'] - 1) * 100:+.1f}%)")
                    risk_p += diff
                if ln["qty_m"] > po_ln["received"] + pol["quantity_tolerance"]:
                    short.append(f"line {ln['line_no']} {ln['item_id']} bills {ln['qty_m']:g}, {po_ln['received']:g} received"
                                 + (" (delivery closed)" if po_ln["complete"] else " (delivery open)"))
                    risk_q += (ln["qty_m"] - po_ln["received"]) * min(ln["price_m"], ln["expected"]) * fx
            if on["price"] and over:
                fails["price"] = ("Unit price above the order: " + "; ".join(over) + ".", round(risk_p, 2))
            if on["quantity"] and short:
                fails["quantity"] = ("Billed for more than was received: " + "; ".join(short) + ".", round(risk_q, 2))

        if p["charge"] > 0:
            charge_aud = round(p["charge"] * fx, 2)
            inside = on["charge_tolerance"] and charge_aud <= pol["charge_max_aud"] \
                and p["charge"] <= pol["charge_max_pct_of_subtotal"] * p["subtotal"]
            if not on["unplanned_charge"] or inside:
                d["flags"].append("charge_accepted")
            else:
                fails["unplanned_charge"] = (f"Freight of {p['charge']:,.2f} is not on the order and is above policy "
                                             f"(${pol['charge_max_aud']:.0f} and {pol['charge_max_pct_of_subtotal']:.0%} of the subtotal).",
                                             charge_aud)
    held = sum(1 for d in docs if d["fails"])
    stage("match", len(ok), len(ok), 0, "each line joined to its order line and to what was received")
    stage("checks", len(docs), len(docs) - held, held, "ten checks in a fixed order; the first to fail is the reason on the exception")

    # ---- publish ----------------------------------------------------------------
    inv_rows, line_rows, exc_rows = [], [], []
    for d in docs:
        p, s = d["parsed"], d["supplier"]
        checks = [c for c in CHECK_ORDER if c in d["fails"]]
        d["check_id"] = checks[0] if checks else None
        d["status"] = "held" if checks else "matched"
        base = {"doc_id": d["doc_id"], "month": d["month"], "received_at": d["received_at"], "channel": d["channel"]}
        known = p is not None and s is not None
        inv_rows.append({
            **base, "layout": p["layout"] if p else None, "file": d["file"], "raw_row": d["raw_row"],
            "supplier_id": s["supplier_id"] if s else None, "supplier_name": s["name"] if s else None,
            "invoice_number": p["invoice_number"] if p else None,
            "invoice_number_normalised": d.get("norm_number"), "invoice_date": p["invoice_date"] if p else None,
            "po_number": p["po_number"] if p else None, "entity": s["entity"] if s else None,
            "currency": p["currency"] if p else None, "subtotal": p["subtotal"] if p else None,
            "charges": p["charge"] if p else None, "tax": p["tax"] if p else None, "total": p["total"] if p else None,
            "total_aud": d.get("total_aud") if known else None, "status": d["status"], "check_id": d["check_id"],
            "checks": ",".join(checks), "flags": ",".join(d["flags"]),
            "at_risk_aud": d["fails"][checks[0]][1] if checks else 0.0,
            "bank_matches_master": (p["bsb"], p["account"]) == (s["bsb"], s["account"]) if known else None,
            "line_count": len(p["lines"]) if p else 0,
        })
        if checks:
            exc_rows.append({
                "exception_id": "EX-" + d["doc_id"][4:], **base, "supplier_id": s["supplier_id"] if s else None,
                "supplier_name": s["name"] if s else None, "invoice_number": p["invoice_number"] if p else None,
                "check_id": checks[0], "checks": ",".join(checks), "reason": d["fails"][checks[0]][0],
                "total_aud": d.get("total_aud") if known else None, "at_risk_aud": d["fails"][checks[0]][1],
            })
        if known:
            for ln in p["lines"]:
                po_ln = ln["po_line"]
                line_rows.append({
                    "doc_id": d["doc_id"], "month": d["month"], "line_no": ln["line_no"], "item_id": ln["item_id"] or None,
                    "description": ln["description"], "qty": ln["qty"], "uom": ln["uom"], "unit_price": ln["unit_price"],
                    "amount": ln["amount"], "amount_aud": round(ln["amount"] * d["fx"], 2), "qty_matched": ln["qty_m"],
                    "unit_price_matched": round(ln["price_m"], 6), "po_number": d["po"]["po_number"] if d["po"] else None,
                    "po_line_no": po_ln["line_no"] if po_ln else None, "po_qty": po_ln["qty"] if po_ln else None,
                    "po_unit_price": po_ln["unit_price"] if po_ln else None, "expected_unit_price": ln["expected"],
                    "received_qty": po_ln["received"] if po_ln else None,
                    "price_variance_pct": round(ln["price_m"] / ln["expected"] - 1, 6) if po_ln else None,
                })

    dim_supplier = pd.DataFrame([{
        "supplier_id": s["supplier_id"], "name": s["name"], "country": s["country"], "currency": s["currency"],
        "tax_code": s["tax_code"], "entity": s["entity"], "payment_terms_days": int(s["payment_terms_days"]),
        "po_mandatory": s["po_mandatory"] == "Y", "category": s["category"], "bank_masked": mask_account(s["bsb"], s["account"]),
        "bank_verified_on": date.fromisoformat(s["bank_verified_on"]), "sender_domain": s["sender_domain"]} for s in suppliers.values()])
    dim_item = pd.DataFrame([{k: i[k] for k in ("item_id", "description", "category", "base_uom", "pack_uom", "pack_size")}
                             for i in items.values()])
    fact_po_line = pd.DataFrame([{
        "po_number": p["po_number"], "line_no": ln["line_no"], "supplier_id": p["supplier_id"], "entity": p["entity"],
        "order_date": p["order_date"], "currency": p["currency"], "item_id": ln["item_id"], "qty": ln["qty"], "uom": ln["uom"],
        "unit_price": ln["unit_price"], "line_total": round(ln["qty"] * ln["unit_price"], 2), "received_qty": ln["received"],
        "delivery_complete": ln["complete"], "invoices": len(p["invoices"])} for p in pos.values() for ln in p["lines"].values()])
    fact_receipt = pd.DataFrame([{
        "receipt_id": g["receipt_id"], "po_number": g["po_number"], "line_no": int(g["line_no"]),
        "received_date": date.fromisoformat(g["received_date"]), "qty_received": float(g["qty_received"]),
        "delivery_complete": g["delivery_complete"] == "Y", "docket": g["docket"]} for g in erp["goods_receipts"]])
    tables = {
        "dim_supplier": dim_supplier, "dim_item": dim_item, "fact_po_line": fact_po_line, "fact_receipt": fact_receipt,
        "fact_invoice": pd.DataFrame(inv_rows), "fact_invoice_line": pd.DataFrame(line_rows),
        "exceptions": pd.DataFrame(exc_rows, columns=["exception_id", "doc_id", "month", "received_at", "channel",
                                                      "supplier_id", "supplier_name", "invoice_number", "check_id",
                                                      "checks", "reason", "total_aud", "at_risk_aud"]),
    }
    hashes = []
    for name in ("dim_supplier", "dim_item", "fact_po_line", "fact_receipt"):
        hashes.append({"partition": name, "rows": len(tables[name]), "sha256": frame_digest(tables[name])})
    for name in ("fact_invoice", "fact_invoice_line", "exceptions"):
        for month in ref.MONTHS:
            part = tables[name][tables[name]["month"] == month]
            hashes.append({"partition": f"{name}/{month}", "rows": len(part), "sha256": frame_digest(part)})
    stage("publish", len(docs), sum(len(t) for t in tables.values()), 0,
          f"{len(tables)} governed tables, {len(hashes)} partitions digested")
    return PipelineResult(files=files, tables=tables, partition_hashes=pd.DataFrame(hashes), stages=stages, docs=docs,
                          pos=pos, suppliers=suppliers, items=items, notices=notices)
