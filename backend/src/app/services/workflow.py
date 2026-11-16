"""Governed writes: deciding a held invoice, approving a rule change, reset.

Every write is token-gated by the router, audit-logged here, and refused - not
warned - when the rule says no:

  - the agent's service identity cannot decide anything
  - a held invoice is decided once
  - a bank detail hold cannot be released from this queue by anyone
  - an exact duplicate cannot be paid from this queue by anyone
  - the proposer of a rule change cannot approve it

Approving a proposal reprocesses the quarter from the raw files and replaces
the governed tables, so every page moves on the next request. Nothing is
patched in place.
"""

from __future__ import annotations

import json
import time
from datetime import datetime

from fastapi import HTTPException

from src.app.pipeline.ablation import run_ablation
from src.app.pipeline.cases import load_truth
from src.app.pipeline.persist import persist_governed, replace
from src.app.pipeline.stages import run_pipeline
from src.app.services import db
from src.app.services.triage import PAYING
from src.settings import settings

SERVICE_IDENTITIES = {"ap-automation", "triage-agent"}
ACTIONS = {"reject_duplicate", "short_pay_po_price", "pay_received_quantity", "hold_until_receipt", "route_to_buyer",
           "return_to_supplier", "route_to_budget_owner", "propose_po_match", "key_manually", "release_for_payment",
           "escalate_to_human"}


def _now() -> datetime:
    return datetime.now().replace(microsecond=0)


def _audit(cur, actor: str, action: str, subject: str, outcome: str, detail: dict | str) -> None:
    cur.execute("INSERT INTO audit_log VALUES (?, ?, ?, ?, ?, ?)", [
        _now(), actor, action, subject, outcome, detail if isinstance(detail, str) else json.dumps(detail, default=str)])


def _refuse(cur, actor: str, action: str, subject: str, status: int, reason: str) -> None:
    _audit(cur, actor, action, subject, "refused", reason)
    raise HTTPException(status_code=status, detail=reason)


def approved_notices(cur=None) -> frozenset[str]:
    sql = "SELECT notice_id FROM proposals WHERE status = 'approved'"
    rows = cur.execute(sql).fetchall() if cur is not None else [(r["notice_id"],) for r in db.rows(sql)]
    return frozenset(r[0] for r in rows)


def decide_exception(exception_id: str, actor: str, action: str, note: str = "") -> dict:
    with db.writing() as cur:
        rows = cur.execute("SELECT check_id, reason FROM exceptions WHERE exception_id = ?", [exception_id]).fetchall()
        if not rows:
            raise HTTPException(status_code=404, detail=f"No held invoice {exception_id}.")
        check_id, reason = rows[0]
        verb = f"decide:{action}"
        if action not in ACTIONS:
            raise HTTPException(status_code=400, detail=f"{action} is not an action a person can take here.")
        if actor.strip().lower() in SERVICE_IDENTITIES:
            _refuse(cur, actor, verb, exception_id, 403,
                    f"{actor} is the automation's own identity. It proposes; a person decides.")
        prior = cur.execute("SELECT action, actor FROM exception_decisions WHERE exception_id = ?", [exception_id]).fetchall()
        if prior:
            _refuse(cur, actor, verb, exception_id, 409,
                    f"{exception_id} was already decided ({prior[0][0]}) by {prior[0][1]}. A held invoice is decided once.")
        if check_id == "bank_details" and action != "escalate_to_human":
            _refuse(cur, actor, verb, exception_id, 409,
                    "A change of bank details cannot be actioned from this queue. It is verified by calling a number "
                    "already on file, and the supplier master is updated by someone other than the person paying.")
        if check_id == "duplicate" and action in PAYING and "invoice number" in reason:
            _refuse(cur, actor, verb, exception_id, 409,
                    "This invoice has the same supplier and number as one already received. It cannot be paid from this "
                    "queue; if the first was reversed, the credit note has to be recorded first.")
        cur.execute("INSERT INTO exception_decisions VALUES (?, ?, ?, ?, ?)", [exception_id, action, actor, _now(), note])
        _audit(cur, actor, verb, exception_id, "done", note or action)
        return {"exception_id": exception_id, "action": action, "decided_by": actor}


def _snapshot(cur) -> dict:
    held, matched, risk = cur.execute(
        "SELECT count(*) FILTER (WHERE status = 'held'), count(*) FILTER (WHERE status = 'matched'), "
        "coalesce(sum(at_risk_aud) FILTER (WHERE status = 'held'), 0) FROM fact_invoice").fetchall()[0]
    return {"held": int(held), "matched": int(matched), "straight_through": round(matched / (held + matched), 4),
            "held_for_price": int(cur.execute("SELECT count(*) FROM fact_invoice WHERE check_id = 'price'").fetchall()[0][0]),
            "at_risk_aud": round(float(risk), 2)}


def decide_proposal(proposal_id: str, actor: str, approve: bool, note: str = "") -> dict:
    with db.writing() as cur:
        rows = cur.execute("SELECT status, proposed_by, decided_by, notice_id FROM proposals WHERE proposal_id = ?",
                           [proposal_id]).fetchall()
        if not rows:
            raise HTTPException(status_code=404, detail=f"No proposal {proposal_id}.")
        status, proposed_by, decided_by, notice_id = rows[0]
        action = "approve" if approve else "reject"
        if status != "pending":
            _refuse(cur, actor, action, proposal_id, 409,
                    f"{proposal_id} was already {status} by {decided_by}. A proposal is decided once.")
        if actor.strip().lower() == str(proposed_by).lower() or actor.strip().lower() in SERVICE_IDENTITIES:
            _refuse(cur, actor, action, proposal_id, 403,
                    f"{actor} proposed {proposal_id} and cannot also decide it. Someone else has to.")
        now = _now()
        cur.execute("UPDATE proposals SET status = ?, decided_by = ?, decided_at = ?, decision_note = ? WHERE proposal_id = ?",
                    ["approved" if approve else "rejected", actor, now, note, proposal_id])
        if not approve:
            _audit(cur, actor, "reject", proposal_id, "done", note or "rejected")
            return {"proposal_id": proposal_id, "status": "rejected"}

        before = _snapshot(cur)
        notices = approved_notices(cur)
        w0 = time.perf_counter()
        result = run_pipeline(settings.raw_dir, approved_notices=notices)
        ablation = run_ablation(settings.raw_dir, result, notices)
        wall_ms = (time.perf_counter() - w0) * 1000
        n = int(cur.execute("SELECT count(*) FROM runs").fetchall()[0][0]) + 1
        run = {"run_id": f"RUN-{n:04d}", "kind": "reprocess", "trigger": f"{proposal_id} approved by {actor}",
               "started_at": now, "git_sha": settings.git_sha, "approved_notices": sorted(notices), "wall_ms": round(wall_ms, 1)}
        persist_governed(cur, result, run, load_truth(settings.truth_path))
        replace(cur, "ablation", ablation)
        after = _snapshot(cur)
        _audit(cur, actor, "approve", proposal_id, "done", {"run_id": run["run_id"], "notice": notice_id,
                                                           "before": before, "after": after})
        return {"proposal_id": proposal_id, "status": "approved", "run_id": run["run_id"], "wall_ms": run["wall_ms"],
                "before": before, "after": after}


def reset(actor: str) -> dict:
    db.reset_to_build()
    with db.writing() as cur:
        _audit(cur, actor, "reset", "workbench", "done", "restored the built state")
    return {"status": "reset"}
