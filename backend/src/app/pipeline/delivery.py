"""The delivery record - roadmap, requirements, RAID log, acceptance scenarios -
and the published measures. Kept as YAML in the repository, so a change to
scope or to a definition is a reviewed commit like any other.

Acceptance scenarios and measures are not prose: each carries a query, run
against the governed tables, and the page shows what it returned.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]


@lru_cache(maxsize=None)
def load(rel: str) -> dict:
    return yaml.safe_load((REPO_ROOT / rel).read_text(encoding="utf-8"))


def run_uat(con) -> pd.DataFrame:
    rows = []
    for s in load("delivery/uat.yaml")["scenarios"]:
        actual = con.execute(s["sql"]).fetchall()[0][0]
        actual = 0 if actual is None else float(actual)
        rows.append({"id": s["id"], "owner": s["owner"], "scenario": s["scenario"], "measures": s["measures"],
                     "expect": float(s["expect"]), "actual": actual, "passed": actual == float(s["expect"])})
    return pd.DataFrame(rows)


def run_measures(con) -> list[dict]:
    out = []
    for m in load("semantic/measures.yaml")["measures"]:
        value = con.execute(m["sql"]).fetchall()[0][0]
        out.append({**m, "value": None if value is None else float(value)})
    return out
