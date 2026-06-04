from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.config import get_settings
from app.core.deps import get_current_user
from app.core.auth import AuthUser
from app.schemas.api_models import WatcherStartRequest, WatcherStatus
from app.services.memory_service import get_memory_manager
from app.services import watcher_service

router = APIRouter()


@router.post("/watcher/start", response_model=WatcherStatus)
def start_watcher(
    body: WatcherStartRequest,
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> WatcherStatus:
    settings = get_settings()
    memory = get_memory_manager()
    if body.experiment_id:
        memory.set_current_experiment(body.experiment_id, user.id)
    directory = body.directory or memory.get_var("watcher_directory") or ""
    port = body.port or settings.watcher_port
    return watcher_service.start(directory=directory, port=port, results_dir=body.results_dir)


@router.post("/watcher/stop", response_model=WatcherStatus)
def stop_watcher(
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> WatcherStatus:
    return watcher_service.stop()


@router.get("/watcher/status", response_model=WatcherStatus)
def get_watcher_status(
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> WatcherStatus:
    return watcher_service.status()
