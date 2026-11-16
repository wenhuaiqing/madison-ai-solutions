"""Read endpoints, one per page. Thin: the SQL lives in services/analytics.py."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from src.app.services import analytics, timings

router = APIRouter(prefix="/api", tags=["pages"])

for _name in ("overview", "process", "lakehouse", "exceptions", "selfserve", "value", "risk"):
    router.add_api_route(f"/{_name}", getattr(analytics, _name), methods=["GET"], name=_name)
router.add_api_route("/delivery", analytics.delivery_page, methods=["GET"], name="delivery")
router.add_api_route("/triage", analytics.triage_page, methods=["GET"], name="triage")


@router.get("/lineage")
def lineage(doc_id: str) -> dict:
    try:
        return analytics.lineage(doc_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/exceptions/{exception_id}")
def exception_detail(exception_id: str) -> dict:
    try:
        return analytics.exception_detail(exception_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/operations")
def operations() -> dict:
    return analytics.operations(timings.summary())
