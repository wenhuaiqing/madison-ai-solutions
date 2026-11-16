"""The delivery record is checked like code: every requirement names a test
that exists, every acceptance scenario runs, every measure evaluates."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.app.pipeline import delivery

TESTS = Path(__file__).parent


def test_every_requirement_names_a_test_that_exists():
    reqs = delivery.load("delivery/requirements.yaml")["requirements"]
    scenarios = {s["id"] for s in delivery.load("delivery/uat.yaml")["scenarios"]}
    assert len(reqs) >= 10
    for r in reqs:
        assert r["proved_by"], r["id"]
        for ref in r["proved_by"]:
            file, _, name = ref.partition("::")
            assert re.search(rf"^def {name}\(", (TESTS / file).read_text(encoding="utf-8"), flags=re.M), ref
        assert set(r["uat"]) <= scenarios, r["id"]


@pytest.mark.needs_build
def test_every_acceptance_scenario_passes_and_every_measure_evaluates(fresh_db):
    assert fresh_db.scalar("SELECT count(*) FROM uat_results") == len(delivery.load("delivery/uat.yaml")["scenarios"])
    assert fresh_db.scalar("SELECT count(*) FROM uat_results WHERE NOT passed") == 0
    cur = fresh_db.connection().cursor()
    measures = delivery.run_measures(cur)
    cur.close()
    assert all(m["value"] is not None for m in measures)
    ids = {m["id"] for m in measures}
    for e in delivery.load("semantic/enquiries.yaml")["enquiries"]:
        if e["route"] == "measure":
            assert e["answer"] in ids, e["id"]
        elif e["route"] == "query":
            from src.app.services import sql_validator
            v = sql_validator.validate(e["answer"])
            assert v.ok, (e["id"], v.errors)
            fresh_db.query(v.sql)


def test_the_raid_log_has_owners_and_reasons():
    raid = delivery.load("delivery/raid.yaml")
    assert all(r["mitigation"] and r["owner"] for r in raid["risks"])
    assert all(d["why"] and d["alternatives"] for d in raid["decisions"])
