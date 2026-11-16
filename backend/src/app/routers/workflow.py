"""Governed writes. Token-gated; the rules live in services/workflow.py."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from src.app.services import workflow
from src.app.services.auth import actor, require_write_token

router = APIRouter(prefix="/api", tags=["workflow"], dependencies=[Depends(require_write_token)])


class Note(BaseModel):
    note: str = Field(default="", max_length=400)


class ExceptionDecision(Note):
    action: str = Field(max_length=40)


@router.post("/exceptions/{exception_id}/decide")
async def decide(exception_id: str, body: ExceptionDecision, request: Request) -> dict:
    return await asyncio.to_thread(workflow.decide_exception, exception_id, actor(request), body.action, body.note)


@router.post("/proposals/{proposal_id}/approve")
async def approve(proposal_id: str, body: Note, request: Request) -> dict:
    # Reprocessing the quarter takes a moment; keep the event loop free meanwhile.
    return await asyncio.to_thread(workflow.decide_proposal, proposal_id, actor(request), True, body.note)


@router.post("/proposals/{proposal_id}/reject")
async def reject(proposal_id: str, body: Note, request: Request) -> dict:
    return await asyncio.to_thread(workflow.decide_proposal, proposal_id, actor(request), False, body.note)


@router.post("/reset")
async def reset(request: Request) -> dict:
    return await asyncio.to_thread(workflow.reset, actor(request))
