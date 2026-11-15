"""Per-user engine API used by the webapp (``/v3``).

Authentication is the caller's own Supabase access token; the admin key plays
no part. The endpoints are stateless: the client sends the sessions it already
holds and receives a versioned result. This server stores no training data and
writes none of it to its logs.
"""
from __future__ import annotations

import threading

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import ValidationError

from app.auth_supabase import RateLimiter, current_user
from app.config import settings
from app.science import CONTRACT_VERSION, ENGINE_VERSION
from app.science.concurrent import MODEL_VERSION
from app.science.concurrent_service import plan_week
from app.science.contract import EngineRequest, PlanRequest
from app.science.service import evaluate

router = APIRouter(prefix="/v3")
MAX_ENGINE_BODY = 8 * 1024 * 1024
engine_limit = RateLimiter(limit=30, window_seconds=60)
# A per-user request limit alone does not bound concurrent CPU/memory use.
_calculation_slots = threading.BoundedSemaphore(2)


def _calculate(function, payload):
    if not _calculation_slots.acquire(blocking=False):
        raise HTTPException(429, "Engine busy; try again shortly", headers={"Retry-After": "10"})
    try:
        return function(payload)
    finally:
        _calculation_slots.release()


@router.get("/engine/version")
def engine_version():
    return {"engine_version": ENGINE_VERSION, "contract_version": CONTRACT_VERSION, "model_version": MODEL_VERSION,
            "accounts_configured": bool(settings.supabase_url)}


async def _body(request: Request) -> bytes:
    """Read at most MAX_ENGINE_BODY bytes; a larger upload is cut off instead of buffered."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_ENGINE_BODY:
        raise HTTPException(413, "Request too large")
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_ENGINE_BODY:
            raise HTTPException(413, "Request too large")
    return bytes(data)


def _parse(model, body: bytes):
    try:
        payload = model.model_validate_json(body)
    except ValidationError as error:
        # Field paths only: submitted training data is never echoed back.
        paths = sorted({".".join(str(part) for part in item["loc"]) for item in error.errors()})[:20]
        raise HTTPException(422, {"message": "Invalid engine request", "fields": paths}) from None
    if payload.contractVersion != CONTRACT_VERSION:
        raise HTTPException(409, {"message": "Unsupported contract version", "supported": CONTRACT_VERSION})
    return payload


@router.post("/engine/evaluate")
async def engine_evaluate(request: Request, user: str = Depends(current_user)):
    engine_limit.check(user)
    payload = _parse(EngineRequest, await _body(request))
    return await run_in_threadpool(_calculate, evaluate, payload)       # CPU work must not block other requests


@router.post("/engine/plan")
async def engine_plan(request: Request, user: str = Depends(current_user)):
    engine_limit.check(user)
    payload = _parse(PlanRequest, await _body(request))
    try:
        return await run_in_threadpool(_calculate, plan_week, payload)
    except ValueError as error:
        raise HTTPException(422, {"message": str(error), "fields": []}) from None
