from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from uuid import uuid4

from app.core.deps import get_current_user
from app.core.auth import AuthUser
from app.schemas.api_models import WorkflowRunRequest, WorkflowRunResponse, WorkflowStatus
from app.services.memory_service import get_memory_manager
from app.services.workflow_service import (
    apply_named_workflow,
    delete_named_workflow,
    export_workflow_json,
    get_workflow_session,
    load_named_workflow,
    patch_workflow_session,
    run_demo_workflow,
    save_named_workflow,
    start_workflow,
    stop_workflow,
)

router = APIRouter()
_workflows: dict[str, WorkflowStatus] = {}


class WorkflowStepModel(BaseModel):
    name: str
    automatic: bool = False
    description: Optional[str] = None


class WorkflowSessionPatch(BaseModel):
    experiment_id: Optional[int] = None
    workflow_name: Optional[str] = None
    workflow_steps: Optional[List[WorkflowStepModel]] = None
    routing_mode: Optional[str] = None
    workflow_ml_model_choice: Optional[str] = None
    workflow_index: Optional[int] = None
    workflow_step: Optional[str] = None
    auto_ml_after_curve_fitting: Optional[bool] = None
    auto_route_to_analysis: Optional[bool] = None


class WorkflowSaveRequest(BaseModel):
    experiment_id: Optional[int] = None
    name: str
    steps: List[WorkflowStepModel]
    apply: bool = False


class WorkflowNameRequest(BaseModel):
    experiment_id: Optional[int] = None
    name: str


def _memory(experiment_id: Optional[int], user: AuthUser):
    memory = get_memory_manager()
    if experiment_id:
        memory.set_current_experiment(experiment_id, user.id)
    return memory


@router.get("/workflows/session")
def workflow_session_get(
    user: Annotated[AuthUser, Depends(get_current_user)],
    experiment_id: Optional[int] = None,
) -> dict:
    return get_workflow_session(_memory(experiment_id, user))


@router.patch("/workflows/session")
def workflow_session_patch(
    body: WorkflowSessionPatch,
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> dict:
    memory = _memory(body.experiment_id, user)
    steps = None
    if body.workflow_steps is not None:
        steps = [s.model_dump() for s in body.workflow_steps]
    return patch_workflow_session(
        memory,
        workflow_name=body.workflow_name,
        workflow_steps=steps,
        routing_mode=body.routing_mode,
        workflow_ml_model_choice=body.workflow_ml_model_choice,
        workflow_index=body.workflow_index,
        workflow_step=body.workflow_step,
        auto_ml_after_curve_fitting=body.auto_ml_after_curve_fitting,
        auto_route_to_analysis=body.auto_route_to_analysis,
    )


@router.post("/workflows/save")
def workflow_save(
    body: WorkflowSaveRequest,
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> dict:
    memory = _memory(body.experiment_id, user)
    steps = [s.model_dump() for s in body.steps]
    out = save_named_workflow(memory, body.name, steps)
    if body.apply:
        out.update(apply_named_workflow(memory, body.name))
    return out


@router.post("/workflows/load")
def workflow_load(
    body: WorkflowNameRequest,
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> dict:
    return load_named_workflow(_memory(body.experiment_id, user), body.name)


@router.post("/workflows/apply")
def workflow_apply(
    body: WorkflowNameRequest,
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> dict:
    return apply_named_workflow(_memory(body.experiment_id, user), body.name)


@router.delete("/workflows/saved")
def workflow_delete(
    user: Annotated[AuthUser, Depends(get_current_user)],
    name: Annotated[str, Query()],
    experiment_id: Optional[int] = None,
) -> dict:
    return delete_named_workflow(_memory(experiment_id, user), name)


@router.post("/workflows/start")
def workflow_start(
    user: Annotated[AuthUser, Depends(get_current_user)],
    experiment_id: Optional[int] = None,
) -> dict:
    return start_workflow(_memory(experiment_id, user))


@router.post("/workflows/stop")
def workflow_stop(
    user: Annotated[AuthUser, Depends(get_current_user)],
    experiment_id: Optional[int] = None,
) -> dict:
    return stop_workflow(_memory(experiment_id, user))


class WorkflowDemoRequest(BaseModel):
    experiment_id: Optional[int] = None
    auto_fit: bool = True


@router.post("/workflows/demo")
def workflow_demo(
    user: Annotated[AuthUser, Depends(get_current_user)],
    body: WorkflowDemoRequest = WorkflowDemoRequest(),
) -> dict:
    return run_demo_workflow(_memory(body.experiment_id, user), auto_fit=body.auto_fit)


@router.get("/workflows/export")
def workflow_export(
    user: Annotated[AuthUser, Depends(get_current_user)],
    experiment_id: Optional[int] = None,
) -> dict:
    memory = _memory(experiment_id, user)
    return {"json": export_workflow_json(memory)}


@router.post("/workflows/run", response_model=WorkflowRunResponse, status_code=202)
def run_workflow(
    body: WorkflowRunRequest,
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> WorkflowRunResponse:
    memory = get_memory_manager()
    memory.set_current_experiment(body.experiment_id, user.id)
    memory.set_var("workflow_active", True)
    memory.set_var("routing_mode", "Autonomous (LLM)" if body.mode == "autonomous" else "Manual")
    if body.steps:
        step_dicts = [{"name": s, "automatic": False} for s in body.steps]
        memory.save_workflow("api_workflow", step_dicts)

    workflow_id = uuid4()
    status = WorkflowStatus(
        workflow_id=workflow_id,
        status="queued",
        current_step=body.steps[0] if body.steps else None,
    )
    _workflows[str(workflow_id)] = status
    return WorkflowRunResponse(workflow_id=workflow_id, status="queued")


@router.get("/workflows/{workflow_id}", response_model=WorkflowStatus)
def get_workflow(
    workflow_id: str,
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> WorkflowStatus:
    from fastapi import HTTPException

    status = _workflows.get(workflow_id)
    if not status:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return status
