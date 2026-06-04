from typing import Annotated, Dict, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.deps import get_current_user
from app.core.auth import AuthUser
from app.services.analysis_service import (
    get_analysis_session,
    patch_analysis_session,
    run_analysis_pipeline,
)
from app.services.memory_service import get_memory_manager

router = APIRouter()


class AnalysisSessionPatch(BaseModel):
    experiment_id: Optional[int] = None
    research_goal: Optional[str] = None


class AnalysisRunRequest(BaseModel):
    experiment_id: Optional[int] = None
    research_goal: Optional[str] = None
    payload: Dict = Field(default_factory=dict)


@router.get("/analysis/session")
def analysis_session_get(
    user: Annotated[AuthUser, Depends(get_current_user)],
    experiment_id: Optional[int] = None,
) -> dict:
    memory = get_memory_manager()
    if experiment_id:
        memory.set_current_experiment(experiment_id, user.id)
    return get_analysis_session(memory)


@router.patch("/analysis/session")
def analysis_session_patch(
    body: AnalysisSessionPatch,
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> dict:
    memory = get_memory_manager()
    if body.experiment_id:
        memory.set_current_experiment(body.experiment_id, user.id)
    return patch_analysis_session(memory, research_goal=body.research_goal)


@router.post("/analysis/run")
def analysis_run(
    body: AnalysisRunRequest,
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> dict:
    memory = get_memory_manager()
    if body.experiment_id:
        memory.set_current_experiment(body.experiment_id, user.id)
    payload = dict(body.payload)
    if body.research_goal:
        payload["research_goal"] = body.research_goal
    return run_analysis_pipeline(memory, payload)
