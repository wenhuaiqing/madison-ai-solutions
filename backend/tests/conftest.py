"""Shared fixtures.

The suite runs against the built database (scripts/build_platform.py). Tests
that write work on a throwaway copy, never the built one.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="workbench-tests-"))
# Point the app at a scratch copy before any src module reads settings.
os.environ["DUCKDB_PATH"] = str(_TMP / "workbench.duckdb")
os.environ["DEMO_WRITE_TOKEN"] = "test-token"
os.environ["LLM_BASE_URL"] = ""
os.environ["LLM_API_KEY"] = ""

from src.app.pipeline.cases import NOT_EXCEPTIONS, load_truth  # noqa: E402
from src.app.pipeline.stages import run_pipeline  # noqa: E402
from src.settings import settings  # noqa: E402

RAW = settings.raw_dir


def pytest_configure(config):
    config.addinivalue_line("markers", "needs_build: requires data/ from scripts/build_platform.py")


def pytest_collection_modifyitems(config, items):
    if not settings.build_db_path.exists() or not RAW.exists():
        skip = pytest.mark.skip(reason="build first: uv run python ../scripts/build_platform.py")
        for item in items:
            if "needs_build" in item.keywords:
                item.add_marker(skip)


@pytest.fixture(scope="session")
def governed():
    return run_pipeline(RAW)


@pytest.fixture(scope="session")
def truth():
    """What the generator seeded. Tests compare the pipeline's findings with it; the pipeline never reads it."""
    return load_truth(settings.truth_path)


@pytest.fixture(scope="session")
def seeded_exceptions(truth):
    return {doc: defect for doc, (defect, _) in truth.items() if defect not in NOT_EXCEPTIONS}


@pytest.fixture()
def fresh_db():
    """A clean copy of the built database for a test that writes."""
    from src.app.services import db
    db.reset_to_build()
    yield db
    db.reset_to_build()


@pytest.fixture()
def client(fresh_db):
    from fastapi.testclient import TestClient

    from src.main import app
    return TestClient(app)


def pytest_sessionfinish(session, exitstatus):
    from src.app.services import db
    try:
        if db._con is not None:
            db._con.close()
    except Exception:  # noqa: BLE001
        pass
    shutil.rmtree(_TMP, ignore_errors=True)
