"""Governed writes: token-gated, audit-logged, and refused when the rule says no."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.needs_build

OP = {"X-Write-Token": "test-token", "X-Actor": "AP team lead"}


def _one(db, where):
    return db.scalar(f"SELECT exception_id FROM exceptions WHERE {where} ORDER BY exception_id LIMIT 1")


def test_writes_need_the_token(client, fresh_db):
    ex = _one(fresh_db, "check_id = 'price'")
    assert client.post(f"/api/exceptions/{ex}/decide", json={"action": "short_pay_po_price"}).status_code == 401
    assert client.post(f"/api/exceptions/{ex}/decide", json={"action": "short_pay_po_price"},
                       headers={"X-Write-Token": "wrong"}).status_code == 401
    assert client.post("/api/proposals/PRP-0001/approve", json={}).status_code == 401
    assert client.post("/api/reset").status_code == 401
    assert fresh_db.scalar("SELECT count(*) FROM exception_decisions") == 0


def test_the_agent_cannot_decide(client, fresh_db):
    ex = _one(fresh_db, "check_id = 'price'")
    r = client.post(f"/api/exceptions/{ex}/decide", json={"action": "short_pay_po_price"},
                    headers={**OP, "X-Actor": "triage-agent"})
    assert r.status_code == 403 and "a person decides" in r.json()["detail"]
    assert fresh_db.scalar("SELECT count(*) FROM audit_log WHERE outcome = 'refused'") == 1


def test_a_held_invoice_is_decided_once(client, fresh_db):
    ex = _one(fresh_db, "check_id = 'price'")
    assert client.post(f"/api/exceptions/{ex}/decide", json={"action": "short_pay_po_price"}, headers=OP).status_code == 200
    again = client.post(f"/api/exceptions/{ex}/decide", json={"action": "release_for_payment"}, headers=OP)
    assert again.status_code == 409
    assert fresh_db.scalar("SELECT action FROM exception_decisions WHERE exception_id = ?", [ex]) == "short_pay_po_price"


def test_a_bank_detail_hold_cannot_be_released(client, fresh_db):
    ex = _one(fresh_db, "check_id = 'bank_details'")
    for action in ("release_for_payment", "short_pay_po_price", "return_to_supplier"):
        r = client.post(f"/api/exceptions/{ex}/decide", json={"action": action}, headers=OP)
        assert r.status_code == 409 and "number" in r.json()["detail"]
    assert client.post(f"/api/exceptions/{ex}/decide", json={"action": "escalate_to_human"}, headers=OP).status_code == 200


def test_an_exact_duplicate_cannot_be_paid(client, fresh_db):
    ex = _one(fresh_db, "check_id = 'duplicate' AND reason LIKE '%invoice number%'")
    assert client.post(f"/api/exceptions/{ex}/decide", json={"action": "release_for_payment"}, headers=OP).status_code == 409
    assert client.post(f"/api/exceptions/{ex}/decide", json={"action": "reject_duplicate"}, headers=OP).status_code == 200


def test_the_proposer_cannot_approve(client, fresh_db):
    r = client.post("/api/proposals/PRP-0001/approve", json={}, headers={**OP, "X-Actor": "ap-automation"})
    assert r.status_code == 403
    assert fresh_db.scalar("SELECT status FROM proposals") == "pending"


def test_approving_the_price_list_reprocesses_from_raw(client, fresh_db):
    before = fresh_db.scalar("SELECT count(*) FROM exceptions")
    held_for_it = fresh_db.scalar("SELECT count(*) FROM cases WHERE label_category = 'new_price_list'")
    r = client.post("/api/proposals/PRP-0001/approve", json={"note": "agreed with the supplier"},
                    headers={**OP, "X-Actor": "Procurement lead"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["before"]["held"] - body["after"]["held"] == held_for_it
    assert fresh_db.scalar("SELECT count(*) FROM exceptions") == before - held_for_it
    assert fresh_db.scalar("SELECT count(*) FROM runs") == 2
    assert fresh_db.scalar("SELECT count(*) FROM uat_results WHERE NOT passed") == 0
    assert client.post("/api/replay").json()["all_match"]
    again = client.post("/api/proposals/PRP-0001/approve", json={}, headers={**OP, "X-Actor": "Procurement lead"})
    assert again.status_code == 409
    assert client.post("/api/reset", headers=OP).status_code == 200
    assert fresh_db.scalar("SELECT count(*) FROM exceptions") == before


def test_every_page_endpoint_answers(client):
    for path in ("meta", "overview", "process", "lakehouse", "exceptions", "triage", "selfserve", "value", "risk",
                 "delivery", "operations"):
        assert client.get(f"/api/{path}").status_code == 200, path
    ex = client.get("/api/exceptions").json()["rows"][0]["exception_id"]
    detail = client.get(f"/api/exceptions/{ex}").json()
    assert detail["document"]["text_masked"] and detail["exception"]["world"]["get_policy"]
    assert client.get("/api/exceptions/EX-999999").status_code == 404
    assert client.post("/api/replay").json()["all_match"]
