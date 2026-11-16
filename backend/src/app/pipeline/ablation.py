"""What each control is worth: switch it off, run the quarter again from the
raw files, and count what would have been paid that should not have been.

Three kinds of answer, kept apart because they are not the same thing:

  paid in error  money that leaves and has to be recovered (a duplicate, an
                 overcharge, goods never received)
  exposure       money released without the approval the policy requires (no
                 order, a changed bank account) - not necessarily lost
  work           nothing is mispaid, but invoices that should match are held
                 and somebody has to clear them
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.app.pipeline.stages import CONTROLS, PipelineResult, run_pipeline

KIND = {
    "duplicate": "paid in error", "price": "paid in error", "quantity": "paid in error", "tax": "paid in error",
    "arithmetic": "paid in error", "currency": "paid in error", "unplanned_charge": "paid in error",
    "bank_details": "exposure", "po_reference": "exposure",
    "uom_normalise": "work", "charge_tolerance": "work",
}


def run_ablation(raw: Path, governed: PipelineResult, approved_notices: frozenset[str] = frozenset()) -> pd.DataFrame:
    base = governed.tables["fact_invoice"]
    base_held = {r.doc_id: (r.check_id, float(r.at_risk_aud), float(r.total_aud or 0)) for r in base.itertuples() if r.status == "held"}
    rows = []
    for control in CONTROLS + ["all_controls_off"]:
        off = {c: False for c in CONTROLS} if control == "all_controls_off" else {control: False}
        inv = run_pipeline(raw, controls=off, approved_notices=approved_notices, hash_files=False).tables["fact_invoice"]
        held_now = set(inv.loc[inv["status"] == "held", "doc_id"])
        released = [d for d in base_held if d not in held_now]
        extra = held_now - set(base_held)
        rows.append({
            "control": control, "kind": KIND.get(control, "everything"),
            "held": len(held_now), "released": len(released), "extra_holds": len(extra),
            "amount_aud": round(sum(base_held[d][1] for d in released), 2),
            "invoice_value_released_aud": round(sum(base_held[d][2] for d in released), 2),
        })
    return pd.DataFrame(rows)
