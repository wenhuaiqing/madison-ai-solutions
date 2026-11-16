"""Re-run the quarter from its raw files and prove the output is the same.

Reads the raw files from disk, re-hashes them against the manifest pinned in
the repository, re-runs the pipeline under the rule changes in force, and
compares every governed partition's digest with the one recorded by the run
that produced the tables the pages are reading.
"""

from __future__ import annotations

import time

from src.app.pipeline.stages import run_pipeline
from src.app.services import db
from src.app.services.workflow import approved_notices
from src.settings import REPO_ROOT, settings

MANIFEST = REPO_ROOT / "infra-azure" / "build.sha256"


def _pinned() -> dict[str, str]:
    if not MANIFEST.exists():
        return {}
    out = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            digest, _, name = line.partition("  ")
            out[name.strip()] = digest.strip()
    return out


def replay() -> dict:
    t0 = time.perf_counter()
    result = run_pipeline(settings.raw_dir, approved_notices=approved_notices())
    wall_ms = (time.perf_counter() - t0) * 1000
    recorded = {r["partition"]: r["sha256"] for r in db.rows("SELECT partition, sha256 FROM partition_hashes")}
    pinned = _pinned()
    partitions = [{"partition": r.partition, "rows": int(r.rows), "sha256": r.sha256,
                   "match": recorded.get(r.partition) == r.sha256} for r in result.partition_hashes.itertuples()]
    files = [{"file": r.file, "rows": int(r.rows), "sha256": r.sha256,
              "match": pinned.get(f"raw/{r.file}") == r.sha256 if pinned else None} for r in result.files.itertuples()]
    return {"wall_ms": round(wall_ms, 1), "files": files, "partitions": partitions,
            "all_match": all(p["match"] for p in partitions) and all(f["match"] in (True, None) for f in files),
            "stages": [s.__dict__ for s in result.stages]}
