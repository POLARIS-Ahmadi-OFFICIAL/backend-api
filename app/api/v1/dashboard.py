from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query

from app.core.deps import get_current_user
from app.core.auth import AuthUser
from app.core.session import SessionContext
from app.schemas.api_models import DashboardDetailResponse, DashboardMetrics, DashboardSummary
from app.services.dashboard_service import build_dashboard_detail
from app.services.memory_service import get_memory_manager

router = APIRouter()


@router.get("/dashboard/summary", response_model=DashboardSummary)
def get_dashboard_summary(
    user: Annotated[AuthUser, Depends(get_current_user)],
    experiment_id: Annotated[Optional[int], Query()] = None,
) -> DashboardSummary:
    memory = get_memory_manager()
    if experiment_id:
        memory.set_current_experiment(experiment_id, user.id)
    ctx = SessionContext.from_memory(memory, experiment_id)
    usage = memory.get_var("agent_usage_counts") or {}
    if not isinstance(usage, dict):
        usage = {}
    return DashboardSummary(
        experiment_id=ctx.experiment_id,
        stage=ctx.stage,
        active_workflow=bool(memory.get_var("workflow_active")),
        last_hypothesis_preview=ctx.extra.get("hypothesis_preview"),
        agent_counts={
            "hypothesis": int(usage.get("hypothesis", 0)) or (1 if ctx.has_hypothesis else 0),
            "experiment": int(usage.get("experiment", 0)) or (1 if ctx.has_experimental_outputs else 0),
            "curve_fitting": int(usage.get("curve_fitting", 0)) or (1 if ctx.has_curve_fitting_results else 0),
            "analysis": int(usage.get("analysis", 0)) or (1 if ctx.has_analysis_results else 0),
        },
    )


@router.get("/dashboard/metrics", response_model=DashboardMetrics)
def get_dashboard_metrics(
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> DashboardMetrics:
    memory = get_memory_manager()
    detail = build_dashboard_detail(memory)
    perf = detail.get("system_performance") or {}
    return DashboardMetrics(
        cpu_percent=perf.get("cpu_percent"),
        memory_percent=perf.get("memory_percent"),
        disk_percent=perf.get("disk_percent"),
        total_events=perf.get("total_events", 0),
        cpu_delta=perf.get("cpu_delta"),
        memory_delta=perf.get("memory_delta"),
        uptime_display=perf.get("uptime_display"),
        uptime_delta_seconds=perf.get("uptime_delta_seconds"),
        events_delta=perf.get("events_delta"),
    )


@router.get("/dashboard/detail", response_model=DashboardDetailResponse)
def get_dashboard_detail(
    user: Annotated[AuthUser, Depends(get_current_user)],
    experiment_id: Annotated[Optional[int], Query()] = None,
) -> DashboardDetailResponse:
    memory = get_memory_manager()
    if experiment_id:
        memory.set_current_experiment(experiment_id, user.id)
    return DashboardDetailResponse(**build_dashboard_detail(memory))
