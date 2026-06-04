from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.deps import get_current_user
from app.core.auth import AuthUser
from app.schemas.api_models import McpOrchestrateRequest, McpOrchestrateResponse
from app.services.memory_service import get_memory_manager
from app.watcher.orchestrator_mcp import OrchestratorService, SearchPapersRequest

router = APIRouter()


@router.post("/mcp/orchestrate", response_model=McpOrchestrateResponse)
def orchestrate_mcp(
    body: McpOrchestrateRequest,
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> McpOrchestrateResponse:
    memory = get_memory_manager()
    if body.experiment_id:
        memory.set_current_experiment(body.experiment_id, user.id)
    svc = OrchestratorService(memory=memory)
    gate = {}
    if body.require_hypothesis_gate:
        gate = svc._history_guard(body.query)
    literature = {}
    try:
        req = SearchPapersRequest(query=body.query, max_candidates=5)
        literature = svc.search_papers(req)
    except Exception as exc:
        literature = {"error": str(exc)}
    return McpOrchestrateResponse(
        status="blocked" if gate.get("blocked") else "ok",
        hypothesis_gate=gate,
        literature=literature if isinstance(literature, dict) else {"result": literature},
    )
