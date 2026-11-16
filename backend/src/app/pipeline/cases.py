"""One case per held invoice: what a person - or the triage agent - would look
at to decide it, frozen as at the quarter's close, and the label it is graded
against.

The snapshot is seven tool answers. Two things are deliberate:

  - bank account numbers are masked before they reach it. The agent is told
    whether the account matches the master, never the account.
  - free text from the invoice is carried under a key that says it is
    untrusted. It is evidence about the document, never an instruction.

Labels come from the generator's truth file, which the pipeline never reads.
"""

from __future__ import annotations

import csv
import json
import statistics
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from src.app.pipeline import reference as ref
from src.app.pipeline.stages import PipelineResult, mask_account

TOOL_NAMES = ["get_invoice", "get_purchase_order", "get_goods_receipts", "get_supplier", "get_related_invoices",
              "get_price_history", "get_policy"]

NOT_EXCEPTIONS = {"uom_pack_billing", "charge_within_policy", "price_list_within_tolerance"}


def load_truth(path: Path) -> dict[str, tuple[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return {r["doc_id"]: (r["defect"], r["detail"]) for r in csv.DictReader(fh)}


def _brief(o: dict) -> dict:
    p = o["parsed"]
    return {"doc_id": o["doc_id"], "invoice_number": p["invoice_number"], "invoice_date": p["invoice_date"].isoformat(),
            "received_at": o["received_at"].isoformat(timespec="minutes"), "total": p["total"],
            "po_number": p["po_number"], "status": o["status"]}


def _order(po: dict, exclude: str) -> dict:
    lines = sorted(po["lines"].values(), key=lambda ln: ln["line_no"])
    return {
        "po_number": po["po_number"], "order_date": po["order_date"].isoformat(), "currency": po["currency"],
        "lines": [{"line_no": ln["line_no"], "item_id": ln["item_id"], "qty": ln["qty"], "uom": ln["uom"],
                   "unit_price": ln["unit_price"], "line_total": round(ln["qty"] * ln["unit_price"], 2)} for ln in lines],
        "order_total": round(sum(ln["qty"] * ln["unit_price"] for ln in lines), 2),
        "other_invoices_on_this_order": [_brief(o) for o in po["invoices"] if o["doc_id"] != exclude],
    }


def build_world(d: dict, res: PipelineResult) -> dict:
    p, s = d["parsed"], d["supplier"]
    policy = {"policy": ref.POLICY, "rules": ref.POLICY_RULES}
    if p is None or s is None:
        return {"get_invoice": {"readable": False, "doc_id": d["doc_id"], "channel": d["channel"], "sender": d["sender"],
                                "received_at": d["received_at"].isoformat(timespec="minutes"),
                                "text_preview_untrusted": d["text"][:60]},
                "get_purchase_order": {"available": False, "reason": "the invoice could not be read"},
                "get_goods_receipts": {"available": False, "reason": "the invoice could not be read"},
                "get_supplier": {"available": False, "reason": "the invoice could not be read"},
                "get_related_invoices": {"available": False, "reason": "the invoice could not be read"},
                "get_price_history": {"available": False, "reason": "the invoice could not be read"},
                "get_policy": policy}

    po = d["po"] if d["po"] is not None and d["po"]["supplier_id"] == s["supplier_id"] else None
    invoice = {
        "readable": True, "doc_id": d["doc_id"], "supplier_name": s["name"], "invoice_number": p["invoice_number"],
        "invoice_date": p["invoice_date"].isoformat(), "received_at": d["received_at"].isoformat(timespec="minutes"),
        "channel": d["channel"], "sender": d["sender"],
        "sender_domain_matches_master": d["sender"].endswith("@" + s["sender_domain"]),
        "po_reference": p["po_number"], "currency": p["currency"],
        "lines": [{"line_no": ln["line_no"], "item_id": ln["item_id"] or None, "description": ln["description"],
                   "qty": ln["qty"], "uom": ln["uom"], "unit_price": ln["unit_price"], "amount": ln["amount"]} for ln in p["lines"]],
        "subtotal": p["subtotal"], "charges": p["charge"], "tax": p["tax"], "total": p["total"], "total_aud": d["total_aud"],
        "remittance_account_masked": mask_account(p["bsb"], p["account"]),
        "remittance_account_matches_master": (p["bsb"], p["account"]) == (s["bsb"], s["account"]),
        "notes_untrusted": p["notes"] or None,
    }

    if po is not None:
        order = {"found": True, **_order(po, d["doc_id"])}
        billed = {ln["item_id"]: ln["qty_m"] for ln in p["lines"]}
        rec_lines = [{"line_no": ln["line_no"], "item_id": ln["item_id"], "ordered": ln["qty"], "received": ln["received"],
                      "billed_in_order_units": billed.get(ln["item_id"]), "delivery_complete": bool(ln["complete"]),
                      "last_receipt_date": ln["last_receipt"], "dockets": ln["dockets"]}
                     for ln in sorted(po["lines"].values(), key=lambda ln: ln["line_no"])]
        receipts = {"available": True, "lines": rec_lines,
                    "fully_received": all(ln["received"] >= ln["ordered"] for ln in rec_lines)}
    else:
        order = {"found": False, "quoted": p["po_number"],
                 "candidates": [{**_order(c, d["doc_id"]), "lines_match_exactly": True} for c in d["candidates"][:3]]}
        receipts = {"available": False, "reason": "no purchase order matched"}

    supplier = {
        "supplier_id": s["supplier_id"], "name": s["name"], "country": s["country"], "currency": s["currency"],
        "tax_code": s["tax_code"], "expected_tax_rate": ref.TAX_RATE_BP[s["tax_code"]] / 10000,
        "po_mandatory": s["po_mandatory"] == "Y", "payment_terms_days": int(s["payment_terms_days"]),
        "bank_on_file_masked": mask_account(s["bsb"], s["account"]), "bank_last_verified": s["bank_verified_on"],
        "sender_domain_on_file": s["sender_domain"],
        "price_notices": [{"notice_id": n["notice_id"], "received_on": n["received_on"],
                           "effective_from": n["effective_from"].isoformat(), "uplift_pct": n["uplift_pct"],
                           "erp_status": n["erp_status"]} for n in res.notices if n["supplier_id"] == s["supplier_id"]],
    }

    related = {"same_number": [_brief(d["dup_of"])] if d.get("dup_of") else [],
               "same_order_and_total": [_brief(o) for o in d.get("dup_like", [])],
               "credit_notes": [], "window_days": ref.POLICY["duplicate_window_days"]}

    since = d["received_at"].date() - timedelta(days=30)
    for n in res.notices:
        if n["supplier_id"] == s["supplier_id"] and p["invoice_date"] >= n["effective_from"]:
            since = n["effective_from"]
    recent = [ln["price_m"] / ln["expected"] - 1 for o in res.docs
              if o["supplier"] is s and o["parsed"]["invoice_date"] >= since
              for ln in o["parsed"]["lines"] if ln.get("expected")]
    median = statistics.median(recent) if recent else 0.0
    history = {
        "lines": [{"line_no": ln["line_no"], "item_id": ln["item_id"], "order_price": ln["po_line"]["unit_price"],
                   "expected_price": ln["expected"], "billed_price_in_order_units": round(ln["price_m"], 4),
                   "variance_pct": round((ln["price_m"] / ln["expected"] - 1) * 100, 2),
                   "billed_uom": ln["uom"], "order_uom": ln["po_line"]["uom"],
                   "pack_size_on_item_master": res.items[ln["item_id"]]["pack_size"] if ln["item_id"] in res.items else None,
                   "line_total_billed": ln["amount"], "line_total_ordered": round(ln["po_line"]["qty"] * ln["po_line"]["unit_price"], 2)}
                  for ln in p["lines"] if ln.get("po_line")],
        "supplier_recent": {"since": since.isoformat(), "lines_billed": len(recent),
                            "lines_above_order": sum(1 for v in recent if v > 0.0005),
                            "median_variance_pct": round(median * 100, 2),
                            "same_variance_on_every_line": len(recent) >= 5 and median > 0.02
                            and all(abs(v - median) < 0.002 for v in recent)},
    }
    return {"get_invoice": invoice, "get_purchase_order": order, "get_goods_receipts": receipts, "get_supplier": supplier,
            "get_related_invoices": related, "get_price_history": history, "get_policy": policy}


def build_cases(res: PipelineResult, truth: dict[str, tuple[str, str]]) -> pd.DataFrame:
    rows = []
    for d in res.docs:
        if not d["fails"]:
            continue
        defect, detail = truth.get(d["doc_id"], ("unknown", ""))
        category = defect if defect in ref.LABEL_ACTION and defect not in NOT_EXCEPTIONS else "unknown"
        rows.append({"exception_id": "EX-" + d["doc_id"][4:], "doc_id": d["doc_id"],
                     "world": json.dumps(build_world(d, res), default=str),
                     "label_category": category, "label_action": ref.LABEL_ACTION[category], "label_detail": detail})
    return pd.DataFrame(rows, columns=["exception_id", "doc_id", "world", "label_category", "label_action", "label_detail"])


__all__ = ["TOOL_NAMES", "NOT_EXCEPTIONS", "build_cases", "build_world", "load_truth", "date"]
