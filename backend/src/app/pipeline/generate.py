"""Generate one quarter of synthetic accounts payable, deterministically.

Writes what a real landing zone would hold: ERP extracts as CSV and the
accounts payable inbox as one JSONL file per month, each record the text of a
supplier invoice in that supplier's own layout. Seeds the defects declared in
reference.py and writes which document carries which to a truth file that sits
outside the landing zone - the pipeline never reads it.

All money is integer cents and all unit prices integer ten-thousandths, so the
output is byte-identical on any machine.
"""

from __future__ import annotations

import csv
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np

from src.app.pipeline import reference as ref


def amount_c(qty: int, price_e4: int) -> int:
    return (qty * price_e4 + 50) // 100


def tax_c(base_c: int, rate_bp: int) -> int:
    return (base_c * rate_bp + 5000) // 10000


def _slug(name: str) -> str:
    return "".join(ch for ch in name.lower().split(" ")[0] if ch.isalpha())


def _fmt_money(c: int) -> str:
    return f"{c / 100:.2f}"


def _fmt_price(e4: int) -> str:
    return f"{e4 / 10000:.4f}"


# ---- the three invoice layouts ----------------------------------------------

def render(inv: dict) -> str:
    s, lay = inv["supplier"], inv["layout"]
    sub = sum(ln["amount_c"] for ln in inv["lines"])
    if lay == "A":
        out = ["TAX INVOICE", f"{s['name']}  ABN {s['abn']}",
               f"Invoice No: {inv['number']}    Invoice Date: {inv['date']:%d/%m/%Y}",
               f"PO Ref: {inv['po'] or ''}    Terms: {s['terms']} days",
               f"Bill To: {ref.ENTITIES[s['entity']]['name']}", f"Currency: {inv['currency']}", "",
               "Ln  Item  Description  Qty  UoM  Unit Price  Amount"]
        for ln in inv["lines"]:
            out.append(f"{ln['line_no']}  {ln['item_id'] or '-'}  {ln['desc']}  {ln['qty']}  {ln['uom']}  "
                       f"{_fmt_price(ln['price_e4'])}  {_fmt_money(ln['amount_c'])}")
        out.append(f"Subtotal: {_fmt_money(sub)}")
        if inv["charge_c"]:
            out.append(f"Freight: {_fmt_money(inv['charge_c'])}")
        out += [f"GST: {_fmt_money(inv['tax_c'])}", f"Total: {_fmt_money(inv['total_c'])}",
                f"Remit To: BSB {inv['bank'][0]}  Account {inv['bank'][1]}"]
        if inv["notes"]:
            out.append(f"Notes: {inv['notes']}")
    elif lay == "B":
        out = ["DOCUMENT=INVOICE", f"SUPPLIER={s['name']}", f"INVOICE_NUMBER={inv['number']}",
               f"INVOICE_DATE={inv['date']:%Y-%m-%d}", f"PURCHASE_ORDER={inv['po'] or ''}",
               f"BILL_TO={ref.ENTITIES[s['entity']]['name']}", f"CURRENCY={inv['currency']}"]
        for ln in inv["lines"]:
            out.append(f"LINE={ln['line_no']};{ln['item_id']};{ln['desc']};{ln['qty']};{ln['uom']};"
                       f"{_fmt_price(ln['price_e4'])};{_fmt_money(ln['amount_c'])}")
        out.append(f"SUBTOTAL={_fmt_money(sub)}")
        if inv["charge_c"]:
            out.append(f"CHARGE=Freight;{_fmt_money(inv['charge_c'])}")
        out += [f"TAX={_fmt_money(inv['tax_c'])}", f"TOTAL={_fmt_money(inv['total_c'])}",
                f"BANK={inv['bank'][0]}/{inv['bank'][1]}"]
        if inv["notes"]:
            out.append(f"NOTE={inv['notes']}")
    else:
        out = [f"HDR|INV|{inv['number']}|{inv['date']:%Y%m%d}|{inv['po'] or ''}|{inv['currency']}",
               f"SUP|{s['supplier_id']}|{s['name']}", f"BUY|{s['entity']}"]
        for ln in inv["lines"]:
            out.append(f"LIN|{ln['line_no']}|{ln['item_id']}|{ln['desc']}|{ln['qty']}|{ln['uom']}|"
                       f"{_fmt_price(ln['price_e4'])}|{_fmt_money(ln['amount_c'])}")
        if inv["charge_c"]:
            out.append(f"CHG|FREIGHT|{_fmt_money(inv['charge_c'])}")
        out += [f"TAX|{_fmt_money(inv['tax_c'])}", f"TOT|{_fmt_money(sub)}|{_fmt_money(inv['total_c'])}",
                f"PAY|{inv['bank'][0]}|{inv['bank'][1]}"]
        if inv["notes"]:
            out.append(f"TXT|{inv['notes']}")
    return "\n".join(out)


BENIGN_NOTES = ["Thank you for your business.", "Goods delivered per attached docket.",
                "Please quote the invoice number with your remittance.", "Backorders will follow on a separate invoice."]


def _retotal(inv: dict) -> None:
    sub = sum(ln["amount_c"] for ln in inv["lines"])
    inv["tax_c"] = tax_c(sub + inv["charge_c"], ref.TAX_RATE_BP[inv["supplier"]["tax_code"]])
    inv["total_c"] = sub + inv["charge_c"] + inv["tax_c"]


def generate(raw: Path, truth_path: Path) -> list[Path]:
    rng = np.random.default_rng(ref.SEED)

    def ri(a: int, b: int) -> int:
        return int(rng.integers(a, b + 1))

    def pick(seq):
        return seq[ri(0, len(seq) - 1)]

    # ---- masters ------------------------------------------------------------
    suppliers: list[dict] = []
    for i, (name, country, focus) in enumerate(ref.GOODS_SUPPLIERS + ref.SERVICE_SUPPLIERS):
        goods = i < len(ref.GOODS_SUPPLIERS)
        c = ref.COUNTRY[country]
        suppliers.append({
            "supplier_id": f"S{i + 1:03d}", "name": name, "country": country, "currency": c["currency"],
            "tax_code": c["tax_code"], "entity": c["entity"], "terms": pick([14, 30, 30, 45]),
            "po_mandatory": "Y" if goods else "N", "focus": focus,
            "bsb": f"{ri(10, 89):02d}{ri(0, 9)}-{ri(100, 999)}", "account": f"{ri(10_000_000, 99_999_999)}",
            "bank_verified_on": date(2025, ri(1, 12), ri(1, 28)), "domain": f"{_slug(name)}.example",
            "abn": f"{ri(10, 99)} {ri(100, 999)} {ri(100, 999)} {ri(100, 999)}",
            "layout": "ABC"[i % 3] if goods else "A", "weight": ri(1, 6) if goods else 0,
            "prefix": "".join(ch for ch in name.upper() if ch.isalpha())[:3], "seq": ri(2000, 9000),
        })
    for s in suppliers:
        s["channel"] = {"A": "email", "B": "portal", "C": "edi"}[s["layout"]]

    items: list[dict] = []
    for cat, n in ref.ITEMS_PER_CATEGORY.items():
        nouns, quals = ref.ITEM_WORDS[cat]
        spec = ref.CATEGORIES[cat]
        for k in range(n):
            pack = pick(spec["packs"]) if spec["packs"] else ("", 1)
            series = k // (len(nouns) * len(quals))
            items.append({
                "item_id": f"{cat}-{k + 1:04d}", "category": cat, "base_uom": spec["base_uom"],
                "description": f"{nouns[k % len(nouns)]} {quals[(k // len(nouns)) % len(quals)]}" + (f" mk{series + 1}" if series else ""),
                "pack_uom": pack[0], "pack_size": pack[1],
            })
    by_cat: dict[str, list[dict]] = {}
    for it in items:
        by_cat.setdefault(it["category"], []).append(it)

    catalogue: dict[str, list[tuple[dict, int]]] = {}
    for s in suppliers[:len(ref.GOODS_SUPPLIERS)]:
        pool = by_cat[s["focus"]]
        order = [int(x) for x in rng.permutation(len(pool))][:min(len(pool), ri(14, 24))]
        lo, hi = ref.CATEGORIES[s["focus"]]["price_e4"]
        catalogue[s["supplier_id"]] = [(pool[j], ri(lo, hi)) for j in sorted(order)]

    # ---- purchase orders, receipts and the invoices they produce -----------------
    goods = suppliers[:len(ref.GOODS_SUPPLIERS)]
    # Integer weights and an integer draw: no floating point decides who is picked.
    cum = np.cumsum([s["weight"] for s in goods])
    pos: list[dict] = []
    invoices: list[dict] = []
    po_no = 104000
    for _ in range(ref.PURCHASE_ORDERS):
        s = goods[int(np.searchsorted(cum, ri(1, int(cum[-1]))))]
        po_no += ri(1, 3)
        order_date = date(2026, 6, 10) + timedelta(days=ri(0, 102))
        cat = catalogue[s["supplier_id"]]
        n_lines = min(pick([1, 1, 2, 2, 2, 3, 3, 4, 5]), len(cat))
        chosen = sorted(int(x) for x in rng.permutation(len(cat))[:n_lines])
        lines = []
        for ln_no, j in enumerate(chosen, start=1):
            it, price = cat[j]
            if it["pack_size"] > 1:
                qty = ri(1, 8 if it["category"] == "CBL" else 20) * it["pack_size"]
            else:
                qty = ri(1, 6) if price > 10_000_000 else ri(1, 24)
            lines.append({"line_no": ln_no, "item": it, "qty": qty, "price_e4": price, "received": []})
        receipt_date = order_date + timedelta(days=ri(10, 25) if s["country"] not in ("AU", "NZ") else ri(3, 15))
        po = {"po": f"PO-{po_no}", "supplier": s, "order_date": order_date, "lines": lines, "receipt_date": receipt_date}
        pos.append(po)
        if receipt_date <= ref.PERIOD_END:
            for ln in lines:
                ln["received"] = [(receipt_date, ln["qty"], True)]
        inv_date = receipt_date + timedelta(days=ri(0, 4))
        received_at = datetime(inv_date.year, inv_date.month, inv_date.day, ri(7, 17), ri(0, 59)) + timedelta(days=ri(0, 3))
        if not (ref.PERIOD_START <= received_at.date() <= ref.PERIOD_END):
            continue
        s["seq"] += ri(1, 4)
        inv = {
            "supplier": s, "po": po["po"], "po_obj": po, "number": f"{s['prefix']}-{s['seq']:06d}", "date": inv_date,
            "received_at": received_at, "currency": s["currency"], "layout": s["layout"], "channel": s["channel"],
            "sender": f"accounts@{s['domain']}", "bank": (s["bsb"], s["account"]), "charge_c": 0,
            "notes": pick(BENIGN_NOTES) if ri(1, 5) == 1 else "", "defect": "", "detail": "",
            "lines": [{"line_no": ln["line_no"], "item_id": ln["item"]["item_id"], "desc": ln["item"]["description"],
                       "qty": ln["qty"], "uom": ln["item"]["base_uom"], "price_e4": ln["price_e4"],
                       "amount_c": amount_c(ln["qty"], ln["price_e4"])} for ln in lines],
        }
        _retotal(inv)
        invoices.append(inv)

    # ---- seed the defects -----------------------------------------------------
    pool = [int(x) for x in rng.permutation(len(invoices))]

    def take(n: int, pred=lambda inv: True) -> list[dict]:
        got, rest = [], []
        for idx in pool:
            if len(got) < n and pred(invoices[idx]):
                got.append(invoices[idx])
            else:
                rest.append(idx)
        pool[:] = rest
        if len(got) < n:
            raise RuntimeError(f"could not seed {n} documents: only {len(got)} candidates")
        return got

    def mark(inv: dict, defect: str, detail: str = "") -> None:
        inv["defect"], inv["detail"] = defect, detail

    def units(inv: dict, ln_no: int) -> int:
        po_ln = inv["po_obj"]["lines"][ln_no - 1]
        return po_ln["qty"] // po_ln["item"]["pack_size"]

    # One supplier's new price list, never loaded into the ERP.
    def sept(s):
        return sum(1 for v in invoices if v["supplier"] is s and v["date"] >= ref.PRICE_LIST_EFFECTIVE)
    riser = max((s for s in goods if s["country"] == "AU"), key=lambda s: (sept(s), s["supplier_id"]))
    fx = ref.FX_E4
    for inv in invoices:
        if inv["supplier"] is not riser:
            continue
        if inv["date"] >= ref.PRICE_LIST_EFFECTIVE:
            trips = False
            for ln in inv["lines"]:
                new = (ln["price_e4"] * (100 + ref.PRICE_LIST_UPLIFT_PCT) + 50) // 100
                trips = trips or amount_c(ln["qty"], new) - ln["amount_c"] > 500
                ln["price_e4"], ln["amount_c"] = new, amount_c(ln["qty"], new)
            _retotal(inv)
            mark(inv, "new_price_list" if trips else "price_list_within_tolerance", ref.PRICE_LIST_NOTICE_ID)
    pool[:] = [i for i in pool if invoices[i]["supplier"] is not riser]

    for inv in take(ref.DEFECTS["currency_mismatch"], lambda v: v["currency"] == "USD"):
        inv["currency"] = "AUD"
        mark(inv, "currency_mismatch", "order in USD, billed in AUD")

    for inv in take(ref.DEFECTS["uom_pack_billing"], lambda v: any(ln["item"]["pack_size"] > 1 for ln in v["po_obj"]["lines"])):
        for ln, po_ln in zip(inv["lines"], inv["po_obj"]["lines"]):
            size = po_ln["item"]["pack_size"]
            if size > 1:
                ln["qty"], ln["uom"], ln["price_e4"] = ln["qty"] // size, po_ln["item"]["pack_uom"], ln["price_e4"] * size
        mark(inv, "uom_pack_billing")

    for inv in take(ref.DEFECTS["price_variance"], lambda v: any(ln["amount_c"] >= 40_000 for ln in v["lines"])):
        ln = next(ln for ln in inv["lines"] if ln["amount_c"] >= 40_000)
        up = ri(3, 18)
        ln["price_e4"] = (ln["price_e4"] * (100 + up) + 50) // 100
        ln["amount_c"] = amount_c(ln["qty"], ln["price_e4"])
        _retotal(inv)
        mark(inv, "price_variance", f"line {ln['line_no']} billed {up}% above the order")

    def aud_sub(v):
        return v["currency"] == "AUD" and sum(ln["amount_c"] for ln in v["lines"]) >= 150_000
    for inv in take(ref.DEFECTS["charge_within_policy"], aud_sub):
        inv["charge_c"] = ri(15, 58) * 100
        _retotal(inv)
        mark(inv, "charge_within_policy")
    for inv in take(ref.DEFECTS["unplanned_charge"]):
        inv["charge_c"] = ri(95, 480) * 100
        _retotal(inv)
        mark(inv, "unplanned_charge", f"freight {inv['charge_c'] / 100:.2f} not on the order")

    for inv in take(ref.DEFECTS["short_delivery"], lambda v: any(units(v, ln["line_no"]) >= 2 for ln in v["lines"])):
        ln = next(ln for ln in inv["lines"] if units(inv, ln["line_no"]) >= 2)
        po_ln = inv["po_obj"]["lines"][ln["line_no"] - 1]
        size = po_ln["item"]["pack_size"]
        got = po_ln["qty"] - size * ri(1, units(inv, ln["line_no"]) - 1)
        po_ln["received"] = [(inv["po_obj"]["receipt_date"], got, True)]
        mark(inv, "short_delivery", f"line {ln['line_no']}: {got} received of {po_ln['qty']}, delivery closed")

    for k, inv in enumerate(take(ref.DEFECTS["receipt_pending"])):
        po = inv["po_obj"]
        partial = k % 3 == 0 and any(units(inv, ln["line_no"]) >= 2 for ln in inv["lines"])
        if partial:
            ln = next(ln for ln in inv["lines"] if units(inv, ln["line_no"]) >= 2)
            po_ln = po["lines"][ln["line_no"] - 1]
            got = po_ln["item"]["pack_size"] * (units(inv, ln["line_no"]) // 2)
            po_ln["received"] = [(po["receipt_date"], got, False)]
            mark(inv, "receipt_pending", f"line {ln['line_no']}: {got} of {po_ln['qty']} received, balance on backorder")
        else:
            for po_ln in po["lines"]:
                po_ln["received"] = []
            mark(inv, "receipt_pending", "nothing received yet")

    for k, inv in enumerate(take(ref.DEFECTS["tax_error"])):
        right = ref.TAX_RATE_BP[inv["supplier"]["tax_code"]]
        wrong = 1000 if right == 0 else (0 if k % 2 == 0 else (1500 if right == 1000 else 1000))
        sub = sum(ln["amount_c"] for ln in inv["lines"])
        inv["tax_c"] = tax_c(sub, wrong)
        inv["total_c"] = sub + inv["tax_c"]
        mark(inv, "tax_error", f"tax charged at {wrong / 100:.0f}%, supplier's code implies {right / 100:.0f}%")

    for inv in take(ref.DEFECTS["arithmetic_error"]):
        over = ri(10, 500) * 100
        inv["total_c"] += over
        mark(inv, "arithmetic_error", f"total overstated by {over / 100:.2f}")

    known_pos = {p["po"] for p in pos}
    for inv in take(ref.DEFECTS["po_reference_error"]):
        digits = inv["po"][3:]
        for i in range(len(digits) - 1, 0, -1):
            swapped = digits[:i - 1] + digits[i] + digits[i - 1] + digits[i + 1:]
            if swapped != digits and f"PO-{swapped}" not in known_pos:
                break
        else:
            swapped = digits[:-1] + "X"
        mark(inv, "po_reference_error", f"{inv['po']} written as PO-{swapped}")
        inv["po"] = f"PO-{swapped}"

    for k, inv in enumerate(take(ref.DEFECTS["bank_detail_change"])):
        inv["bank"] = (f"{ri(10, 89):02d}{ri(0, 9)}-{ri(100, 999)}", f"{ri(10_000_000, 99_999_999)}")
        inv["notes"] = "Please note our updated remittance details, effective immediately."
        if k % 2 == 0:
            inv["sender"] = f"accounts@{inv['supplier']['domain'].replace('.example', '')}-payments.example"
        mark(inv, "bank_detail_change", "remittance account differs from the supplier master")

    unreadable = take(ref.DEFECTS["unreadable"])
    for inv in unreadable:
        mark(inv, "unreadable", "image-only document, no text layer")

    extra: list[dict] = []
    resend_ok = lambda v: v["received_at"].date() <= date(2026, 9, 10)  # noqa: E731
    for k, src in enumerate(take(ref.DEFECTS["duplicate"], resend_ok)):
        dup = {**src, "lines": [dict(ln) for ln in src["lines"]]}
        dup["received_at"] = src["received_at"] + timedelta(days=ri(3, 18), minutes=ri(1, 300))
        dup["channel"], dup["notes"] = "email", ""
        s, seq = src["supplier"], int(src["number"].split("-")[1])
        if k < ref.DUPLICATE_REKEYED:
            s["seq"] += ri(1, 4)
            dup["number"] = f"{s['prefix']}-{s['seq']:06d}"
            dup["date"] = dup["received_at"].date() - timedelta(days=1)
            detail = f"same order and total as {src['number']}, under a new number"
        else:
            dup["number"] = [f"{s['prefix']}{seq:06d}", f"{s['prefix']}-{seq}", f"{s['prefix'].lower()}-{seq:06d}",
                             f"{s['prefix']} {seq:06d}"][k % 4]
            detail = f"{src['number']} resent as {dup['number']}"
        mark(dup, "duplicate", detail)
        extra.append(dup)

    services = suppliers[len(ref.GOODS_SUPPLIERS):]
    for k in range(ref.DEFECTS["no_po"]):
        s = services[k % len(services)]
        d = ref.PERIOD_START + timedelta(days=ri(2, 88))
        s["seq"] += ri(1, 9)
        price = ri(180, 6400) * 10000
        inv = {"supplier": s, "po": None, "po_obj": None, "number": f"{s['prefix']}-{s['seq']:06d}", "date": d,
               "received_at": datetime(d.year, d.month, d.day, ri(7, 17), ri(0, 59)), "currency": s["currency"],
               "layout": s["layout"], "channel": s["channel"], "sender": f"accounts@{s['domain']}",
               "bank": (s["bsb"], s["account"]), "charge_c": 0, "notes": "", "defect": "no_po", "detail": s["focus"],
               "lines": [{"line_no": 1, "item_id": "", "desc": f"{s['focus']} {d:%b %Y}", "qty": 1, "uom": "EA",
                          "price_e4": price, "amount_c": amount_c(1, price)}]}
        _retotal(inv)
        extra.append(inv)

    docs = sorted(enumerate(invoices + extra), key=lambda p: (p[1]["received_at"], p[0]))
    records, truth = [], []
    for n, (_, inv) in enumerate(docs, start=1):
        doc_id = f"DOC-{n:06d}"
        text = ("[scanned image - no text layer]\n" + "".join(pick("#%&@~") for _ in range(40))
                if inv["defect"] == "unreadable" else render(inv))
        records.append({"doc_id": doc_id, "received_at": inv["received_at"].isoformat(timespec="minutes"),
                        "channel": inv["channel"], "sender": inv["sender"], "text": text})
        if inv["defect"]:
            truth.append((doc_id, inv["defect"], inv["detail"]))

    # ---- write the landing zone ------------------------------------------------
    files: list[Path] = []

    def write_csv(rel: str, header: list[str], rows: list[list]) -> None:
        path = raw / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(header)
            w.writerows(rows)
        files.append(path)

    write_csv("erp/suppliers.csv",
              ["supplier_id", "name", "country", "currency", "tax_code", "entity", "payment_terms_days", "po_mandatory",
               "category", "bsb", "account", "bank_verified_on", "sender_domain", "abn"],
              [[s["supplier_id"], s["name"], s["country"], s["currency"], s["tax_code"], s["entity"], s["terms"],
                s["po_mandatory"], s["focus"], s["bsb"], s["account"], s["bank_verified_on"].isoformat(), s["domain"],
                s["abn"]] for s in suppliers])
    write_csv("erp/items.csv", ["item_id", "description", "category", "base_uom", "pack_uom", "pack_size"],
              [[i["item_id"], i["description"], i["category"], i["base_uom"], i["pack_uom"], i["pack_size"]] for i in items])
    write_csv("erp/price_list.csv", ["supplier_id", "item_id", "unit_price", "currency", "valid_from"],
              [[sid, it["item_id"], _fmt_price(p), next(s["currency"] for s in suppliers if s["supplier_id"] == sid),
                "2026-01-01"] for sid, rows in catalogue.items() for it, p in rows])
    write_csv("erp/purchase_orders.csv", ["po_number", "supplier_id", "entity", "order_date", "currency", "status"],
              [[p["po"], p["supplier"]["supplier_id"], p["supplier"]["entity"], p["order_date"].isoformat(),
                p["supplier"]["currency"], "RECEIVED" if any(ln["received"] for ln in p["lines"]) else "OPEN"] for p in pos])
    write_csv("erp/po_lines.csv", ["po_number", "line_no", "item_id", "qty", "uom", "unit_price"],
              [[p["po"], ln["line_no"], ln["item"]["item_id"], ln["qty"], ln["item"]["base_uom"], _fmt_price(ln["price_e4"])]
               for p in pos for ln in p["lines"]])
    gr_rows, n = [], 0
    for p in pos:
        for ln in p["lines"]:
            for when, qty, complete in ln["received"]:
                n += 1
                gr_rows.append([f"GR-{n:06d}", p["po"], ln["line_no"], when.isoformat(), qty, "Y" if complete else "N",
                                f"DKT-{p['po'][3:]}-{ln['line_no']}"])
    write_csv("erp/goods_receipts.csv",
              ["receipt_id", "po_number", "line_no", "received_date", "qty_received", "delivery_complete", "docket"], gr_rows)
    write_csv("erp/supplier_notices.csv",
              ["notice_id", "supplier_id", "received_on", "effective_from", "uplift_pct", "erp_status", "subject"],
              [[ref.PRICE_LIST_NOTICE_ID, riser["supplier_id"], ref.PRICE_LIST_NOTICE_RECEIVED.isoformat(),
                ref.PRICE_LIST_EFFECTIVE.isoformat(), ref.PRICE_LIST_UPLIFT_PCT, "not loaded",
                f"Price list update: all lines up {ref.PRICE_LIST_UPLIFT_PCT}% from {ref.PRICE_LIST_EFFECTIVE:%d/%m/%Y}"]])
    write_csv("erp/fx_rates.csv", ["month", "currency", "rate_to_aud"],
              [[m, cur, f"{e4 / 10000:.4f}"] for cur, months in fx.items() for m, e4 in months.items()])

    for month in ref.MONTHS:
        path = raw / "ap_inbox" / f"invoices_{month}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as fh:
            for r in records:
                if r["received_at"].startswith(month):
                    fh.write(json.dumps(r, ensure_ascii=True) + "\n")
        files.append(path)

    truth_path.parent.mkdir(parents=True, exist_ok=True)
    with truth_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["doc_id", "defect", "detail"])
        w.writerows(truth)
    return files
