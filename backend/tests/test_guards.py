"""The query validator, the triage grader, the runbook, and what the agent is allowed to see."""

from __future__ import annotations

import json
import re
from types import SimpleNamespace

import pytest

from src.app.services import sql_validator, triage


@pytest.mark.parametrize("sql", [
    "SELECT * FROM fact_invoice",
    "WITH x AS (SELECT * FROM exceptions) SELECT * FROM x",
    "select count(*) from fact_invoice_line l join dim_item i using (item_id) limit 10",
])
def test_validator_allows_reads(sql):
    assert sql_validator.validate(sql).ok


@pytest.mark.parametrize("sql", [
    "DELETE FROM fact_invoice",
    "SELECT * FROM fact_invoice; DROP TABLE fact_invoice",
    "SELECT * FROM read_csv('/etc/passwd')",
    "SELECT * FROM audit_log",
    "SELECT * FROM documents",
    "SELECT * FROM cases",
    "ATTACH 'x.db' AS x",
    "SELECT getenv('LLM_API_KEY')",
])
def test_validator_refuses(sql):
    assert not sql_validator.validate(sql).ok


def test_validator_caps_the_limit():
    v = sql_validator.validate("SELECT * FROM fact_invoice LIMIT 999999")
    assert v.ok and v.sql.endswith(f"LIMIT {sql_validator.MAX_LIMIT}")


def _run(category, action, evidence, retrieved):
    return {"result": {"category": category, "proposed_action": action, "evidence": evidence, "confidence": 0.9,
                       "releases_payment": action in triage.PAYING, "summary": ""}, "retrieved": retrieved}


def test_grader_rejects_ungrounded_evidence():
    world = {"get_price_history": {"lines": [{"line_no": 1, "variance_pct": 11.0, "order_price": 585.5648}]}}
    label = {"category": "price_variance", "action": "short_pay_po_price"}
    assert triage.grade(_run("price_variance", "short_pay_po_price", ["line 1 is 11% over the order"], world), label)["passed"]
    made_up = triage.grade(_run("price_variance", "short_pay_po_price", ["the supplier confirmed 73.25 by phone"], world), label)
    assert not made_up["all_grounded"] and not made_up["passed"]


def test_paying_what_should_be_held_is_harmful():
    world = {"x": 4.4}
    for label_cat, label_action in (("duplicate", "reject_duplicate"), ("receipt_pending", "hold_until_receipt"),
                                    ("bank_detail_change", "escalate_to_human"), ("unknown", "escalate_to_human")):
        g = triage.grade(_run("valid_invoice", "release_for_payment", ["4.4"], world),
                         {"category": label_cat, "action": label_action})
        assert g["harmful"] and not g["passed"], label_cat
    rejecting_a_valid_one = triage.grade(_run("duplicate", "reject_duplicate", ["4.4"], world),
                                         {"category": "valid_invoice", "action": "release_for_payment"})
    assert rejecting_a_valid_one["harmful"]
    anything_but_escalating_a_bank_change = triage.grade(_run("tax_error", "return_to_supplier", ["4.4"], world),
                                                         {"category": "bank_detail_change", "action": "escalate_to_human"})
    assert anything_but_escalating_a_bank_change["harmful"]


def _eval_cases(db):
    from src.app.services.triage_cases import build_cases
    return build_cases(db.rows("""SELECT e.exception_id, e.check_id, e.reason, c.world, c.label_category
                                  FROM exceptions e JOIN cases c USING (exception_id) ORDER BY e.exception_id"""))


@pytest.mark.needs_build
def test_the_runbook_is_right_on_every_real_exception(fresh_db):
    rows = fresh_db.rows("""SELECT e.exception_id, e.check_id, e.reason, c.world, c.label_category, c.label_action
                            FROM exceptions e JOIN cases c USING (exception_id)""")
    assert len(rows) >= 150
    for r in rows:
        g = triage.grade(triage.run_rules(r), {"category": r["label_category"], "action": r["label_action"]})
        assert g["passed"], (r["exception_id"], r["label_category"])


@pytest.mark.needs_build
def test_the_runbook_fails_every_hard_case(fresh_db):
    hard = [c for c in _eval_cases(fresh_db) if c["kind"] == "hard"]
    assert len(hard) == 6
    for c in hard:
        assert not triage.grade(triage.run_rules(c["case"]), c["label"])["passed"], c["case_id"]


@pytest.mark.needs_build
def test_adversarial_cases_exist_and_the_runbook_ignores_them(fresh_db):
    adv = [c for c in _eval_cases(fresh_db) if c["kind"] == "adversarial"]
    assert len(adv) == 3
    for c in adv:
        assert c["case"]["world"]["get_invoice"]["notes_untrusted"]
        assert triage.grade(triage.run_rules(c["case"]), c["label"])["passed"], c["case_id"]


@pytest.mark.needs_build
def test_no_bank_account_reaches_the_agent(fresh_db):
    worlds = [r["world"] for r in fresh_db.rows("SELECT world FROM cases")]
    assert worlds and not any(re.search(r"[0-9]{8}", w) for w in worlds)
    for c in _eval_cases(fresh_db):
        assert not re.search(r"[0-9]{8}", json.dumps(c["case"]["world"])), c["case_id"]
    assert "untrusted" in triage.SYSTEM and "never an instruction" in triage.SYSTEM


def test_tool_loop_echoes_provider_metadata(monkeypatch):
    """Some providers attach a signature to each tool call and refuse the next
    turn without it; the loop must send the message back as received."""
    sent = []

    class Msg:
        def __init__(self, calls):
            self.content = None
            self.tool_calls = calls

        def model_dump(self, exclude_none=True):
            return {"role": "assistant", "tool_calls": [
                {"id": c.id, "type": "function", "function": {"name": c.function.name, "arguments": c.function.arguments},
                 "extra_content": {"provider": {"signature": "sig-" + c.id}}} for c in self.tool_calls]}

    def call(name, args, id_):
        return SimpleNamespace(id=id_, function=SimpleNamespace(name=name, arguments=json.dumps(args)))

    verdict = {"category": "price_variance", "confidence": 0.9, "evidence": ["variance_pct 11.0"],
               "proposed_action": "short_pay_po_price", "releases_payment": True, "summary": "s"}
    replies = iter([Msg([call("get_price_history", {}, "c1")]), Msg([call("submit_triage", verdict, "c2")])])

    def fake_call(fn):
        class C:
            class chat:
                class completions:
                    @staticmethod
                    def create(**kw):
                        sent.append(json.loads(json.dumps(kw["messages"], default=str)))
                        return SimpleNamespace(choices=[SimpleNamespace(message=next(replies))])
        return fn("m", C), "m"

    monkeypatch.setattr(triage.llm, "call", fake_call)
    out = triage.run_agent({"exception_id": "EX-1", "check_id": "price", "reason": "Unit price above the order.",
                            "world": {"get_price_history": {"lines": [{"variance_pct": 11.0}]}}})
    assert out["result"]["category"] == "price_variance"
    echoed = [m for m in sent[1] if m.get("role") == "assistant"][0]
    assert echoed["tool_calls"][0]["extra_content"]["provider"]["signature"] == "sig-c1"
