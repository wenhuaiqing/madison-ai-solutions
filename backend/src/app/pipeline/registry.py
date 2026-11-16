"""Proposals: a change to the rules the match runs on, with its evidence
computed from the data and its consequences previewed before anyone decides.

This quarter there is one. A supplier's price notice was received and never
loaded into the ERP, so every one of that supplier's invoices since the
effective date is over the order price by the same percentage. Holding each
of them is correct; clearing them one at a time is waste. The proposal is to
load the notice - a decision for procurement, not for accounts payable and
not for a model.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from src.app.pipeline.stages import PipelineResult, run_pipeline

PROPOSER = "ap-automation"


def price_notice_evidence(res: PipelineResult, notice: dict) -> dict:
    sid, eff, uplift = notice["supplier_id"], notice["effective_from"], notice["uplift_pct"] / 100
    after, before, held, passed, held_aud = [], [], 0, 0, 0.0
    for d in res.docs:
        if d["supplier"] is None or d["supplier"]["supplier_id"] != sid:
            continue
        ratios = [ln["price_m"] / ln["po_line"]["unit_price"] - 1 for ln in d["parsed"]["lines"] if ln.get("po_line")]
        if d["parsed"]["invoice_date"] >= eff:
            after += ratios
            if d["check_id"] == "price":
                held += 1
                held_aud += d["total_aud"]
            elif d["status"] == "matched":
                passed += 1
        elif d["parsed"]["invoice_date"] >= eff - timedelta(days=30):
            before += ratios
    return {
        "notice_id": notice["notice_id"], "supplier_id": sid, "supplier_name": res.suppliers[sid]["name"],
        "notice_received_on": notice["received_on"], "effective_from": eff.isoformat(), "uplift_pct": notice["uplift_pct"],
        "erp_status": notice["erp_status"],
        "lines_since_effective": len(after),
        "lines_at_exactly_the_uplift": sum(1 for v in after if abs(v - uplift) < 0.0006),
        "lines_in_the_30_days_before": len(before),
        "lines_before_at_order_price": sum(1 for v in before if abs(v) < 0.0006),
        "invoices_held": held, "invoices_held_aud": round(held_aud, 2),
        "invoices_passed_within_tolerance": passed,
    }


def price_notice_preview(raw: Path, governed: PipelineResult, notice: dict) -> dict:
    after = run_pipeline(raw, approved_notices={notice["notice_id"]}, hash_files=False)
    b, a = governed.tables["fact_invoice"], after.tables["fact_invoice"]
    released = set(b.loc[b["status"] == "held", "doc_id"]) - set(a.loc[a["status"] == "held", "doc_id"])
    new_holds = set(a.loc[a["status"] == "held", "doc_id"]) - set(b.loc[b["status"] == "held", "doc_id"])
    cost = 0.0
    for d in after.docs:
        if d["supplier"] is not None and d["supplier"]["supplier_id"] == notice["supplier_id"]:
            cost += sum((ln["expected"] - ln["po_line"]["unit_price"]) * ln["qty_m"] * d["fx"]
                        for ln in d["parsed"]["lines"] if ln.get("po_line"))
    return {
        "invoices_released": len(released),
        "invoice_value_released_aud": round(float(b.loc[b["doc_id"].isin(released), "total_aud"].sum()), 2),
        "exceptions_before": int((b["status"] == "held").sum()), "exceptions_after": int((a["status"] == "held").sum()),
        "new_holds": len(new_holds), "price_rise_cost_this_quarter_aud": round(cost, 2),
    }


def proposals_table(raw: Path, governed: PipelineResult, now: datetime) -> pd.DataFrame:
    rows = []
    for n, notice in enumerate([x for x in governed.notices if x["erp_status"] == "not loaded"], start=1):
        ev = price_notice_evidence(governed, notice)
        rows.append({
            "proposal_id": f"PRP-{n:04d}", "kind": "price_list", "notice_id": notice["notice_id"],
            "supplier_id": notice["supplier_id"], "supplier_name": ev["supplier_name"],
            "title": f"Load the price list from {ev['supplier_name']}: {notice['uplift_pct']:g}% from {notice['effective_from']:%d/%m/%Y}",
            "proposed_by": PROPOSER, "proposed_at": now, "status": "pending", "decided_by": None, "decided_at": None,
            "decision_note": None, "evidence": json.dumps(ev), "preview": json.dumps(price_notice_preview(raw, governed, notice)),
        })
    df = pd.DataFrame(rows)
    # All-null columns need a type, or the first approval cannot write to them.
    return df.astype({"decided_by": "string", "decision_note": "string", "decided_at": "datetime64[us]"})
