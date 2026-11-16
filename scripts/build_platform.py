"""Build everything from nothing.

  1. generate the quarter's ERP extracts and invoice inbox (deterministic)
  2. the governed run: parse, match, check, publish - timed and digested
  3. the ablation: every control off in turn, the quarter re-run each time
  4. proposals, with evidence and a preview of what approving would change
  5. write data/workbench.build.duckdb, run the acceptance scenarios
  6. check every raw file and governed partition against the pinned manifest

Usage (from backend/):
  uv run python ../scripts/build_platform.py              # build, verify against the manifest
  uv run python ../scripts/build_platform.py --write-manifest
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import duckdb

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from src.app.pipeline import registry  # noqa: E402
from src.app.pipeline.ablation import run_ablation  # noqa: E402
from src.app.pipeline.cases import load_truth  # noqa: E402
from src.app.pipeline.generate import generate  # noqa: E402
from src.app.pipeline.persist import persist_governed, replace  # noqa: E402
from src.app.pipeline.stages import run_pipeline  # noqa: E402
from src.settings import settings  # noqa: E402

MANIFEST = REPO_ROOT / "infra-azure" / "build.sha256"
# The quarter closes on 30/09; the close run is stamped the next morning.
CLOSE_RUN_AT = datetime(2026, 10, 1, 6, 0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-manifest", action="store_true")
    args = parser.parse_args()

    t0 = time.perf_counter()
    raw = settings.raw_dir
    if raw.exists():
        shutil.rmtree(raw)

    print("1/6 generating the quarter")
    generate(raw, settings.truth_path)
    truth = load_truth(settings.truth_path)

    print("2/6 governed run")
    w0 = time.perf_counter()
    governed = run_pipeline(raw)
    wall_ms = (time.perf_counter() - w0) * 1000
    inv = governed.tables["fact_invoice"]
    print(f"    {len(inv)} documents, {(inv['status'] == 'held').sum()} held, "
          f"{(inv['status'] == 'matched').mean():.1%} straight through")

    print("3/6 ablation (every control off in turn)")
    ablation = run_ablation(raw, governed)
    print(ablation.to_string(index=False))

    print("4/6 proposals")
    proposals = registry.proposals_table(raw, governed, CLOSE_RUN_AT)

    print("5/6 writing the database")
    db_path = Path(settings.build_db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    con = duckdb.connect(str(db_path))
    run = {"run_id": "RUN-0001", "kind": "full build", "trigger": "image build", "started_at": CLOSE_RUN_AT,
           "git_sha": settings.git_sha, "approved_notices": [], "wall_ms": round(wall_ms, 1)}
    persist_governed(con, governed, run, truth)
    replace(con, "ablation", ablation)
    replace(con, "proposals", proposals)
    con.execute("CREATE TABLE kv (k VARCHAR PRIMARY KEY, v VARCHAR)")
    con.execute("INSERT INTO kv VALUES (?, ?)", ["build_seconds", f"{time.perf_counter() - t0:.1f}"])
    con.execute("""CREATE TABLE audit_log (ts TIMESTAMP, actor VARCHAR, action VARCHAR, subject VARCHAR,
                   outcome VARCHAR, detail VARCHAR)""")
    con.execute("""CREATE TABLE exception_decisions (exception_id VARCHAR PRIMARY KEY, action VARCHAR, actor VARCHAR,
                   decided_at TIMESTAMP, note VARCHAR)""")
    con.execute("""CREATE TABLE triage_runs (run_id VARCHAR, ts TIMESTAMP, exception_id VARCHAR, engine VARCHAR,
                   model VARCHAR, ms DOUBLE, steps INTEGER, result VARCHAR, grade VARCHAR, trace VARCHAR)""")
    failed = con.execute("SELECT id, actual FROM uat_results WHERE NOT passed").fetchall()
    con.close()
    if failed:
        print(f"    acceptance scenarios failing: {failed}", file=sys.stderr)
        return 1
    print("    every acceptance scenario passes")

    print("6/6 manifest")
    lines = sorted(f"{h}  {p}" for p, h in zip(governed.partition_hashes["partition"], governed.partition_hashes["sha256"]))
    lines += sorted(f"{h}  raw/{p}" for p, h in zip(governed.files["file"], governed.files["sha256"]))
    body = "\n".join(lines) + "\n"
    if args.write_manifest or not MANIFEST.exists():
        MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST.write_text("# SHA-256 of every raw file and governed partition the build produces.\n"
                            "# Regenerate with: uv run python ../scripts/build_platform.py --write-manifest\n" + body,
                            encoding="utf-8", newline="\n")
        print(f"    manifest written: {len(lines)} entries")
    else:
        pinned = [ln for ln in MANIFEST.read_text(encoding="utf-8").splitlines() if ln and not ln.startswith("#")]
        if sorted(pinned) != sorted(lines):
            missing, unexpected = sorted(set(pinned) - set(lines)), sorted(set(lines) - set(pinned))
            print(f"    MISMATCH against the pinned manifest: {len(missing)} pinned entries not produced, "
                  f"{len(unexpected)} produced entries not pinned", file=sys.stderr)
            for ln in (missing + unexpected)[:6]:
                print(f"      {ln}", file=sys.stderr)
            return 1
        print(f"    verified: {len(lines)} entries match the pinned manifest")

    from src.app.services.db import copy_build
    copy_build()
    print(f"done in {time.perf_counter() - t0:.1f} s -> {db_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
