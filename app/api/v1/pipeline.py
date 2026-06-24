from __future__ import annotations

import uuid
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.graph.interrupts import build_resume_config, build_start_config
from app.graph.pipeline import get_pipeline
from app.graph.state import PolarisGraphState
from app.services.memory_service import get_memory_manager

router = APIRouter(prefix="/pipeline")
_logger = logging.getLogger(__name__)


class StartRequest(BaseModel):
    research_goal: str
    routing_mode: str = "autonomous"


class ResumeRequest(BaseModel):
    thread_id: str
    decision: Dict[str, Any] = {}


def _safe_state(snapshot) -> dict:
    if snapshot is None:
        return {}
    values = getattr(snapshot, "values", None)
    if values is None:
        return {}
    return dict(values)


@router.post("/start")
async def start_pipeline(body: StartRequest) -> Dict[str, Any]:
    """Start the POLARIS pipeline for a new research goal. Returns first interrupt_payload."""
    thread_id = str(uuid.uuid4())
    memory = get_memory_manager()
    memory.set_var("research_goal", body.research_goal)

    initial_state: PolarisGraphState = {
        "stage": "initial",
        "has_hypothesis": False,
        "has_experimental_outputs": False,
        "has_curve_results": False,
        "has_ml_results": False,
        "has_analysis_results": False,
        "hypothesis_ready": False,
        "hypothesis_preview": None,
        "research_goal": body.research_goal,
        "experiment_id": None,
        "current_agent": None,
        "error": None,
        "interrupt_payload": None,
        "routing_mode": body.routing_mode,
        "manual_workflow": [],
        "workflow_index": 0,
    }

    pipeline = get_pipeline()
    config = build_start_config(thread_id)

    try:
        async for _ in pipeline.astream(initial_state, config=config):
            pass
    except Exception as exc:
        _logger.debug("Pipeline paused or errored at start: %s", exc)

    snapshot = await pipeline.aget_state(config)
    state = _safe_state(snapshot)

    return {
        "thread_id": thread_id,
        "interrupt_payload": state.get("interrupt_payload"),
        "state": state,
    }


@router.post("/resume")
async def resume_pipeline(body: ResumeRequest) -> Dict[str, Any]:
    """Resume a paused pipeline thread with a user decision."""
    pipeline = get_pipeline()
    config = build_resume_config(body.thread_id)

    try:
        await pipeline.aupdate_state(config, {"interrupt_payload": None})
        async for _ in pipeline.astream(None, config=config):
            pass
    except Exception as exc:
        _logger.debug("Pipeline paused or errored on resume: %s", exc)

    snapshot = await pipeline.aget_state(config)
    state = _safe_state(snapshot)

    return {
        "thread_id": body.thread_id,
        "interrupt_payload": state.get("interrupt_payload"),
        "state": state,
    }


@router.get("/state/{thread_id}")
async def get_pipeline_state(thread_id: str) -> Dict[str, Any]:
    """Return the current PolarisGraphState for a thread."""
    pipeline = get_pipeline()
    config = build_resume_config(thread_id)
    snapshot = await pipeline.aget_state(config)
    # LangGraph returns a StateSnapshot with metadata=None for threads with no checkpoint
    if snapshot is None or getattr(snapshot, "metadata", None) is None:
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")
    return {"thread_id": thread_id, "state": _safe_state(snapshot)}
