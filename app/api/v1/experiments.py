from datetime import datetime, timezone
from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException

from app.core.deps import get_current_user
from app.core.auth import AuthUser
from app.schemas.api_models import Experiment, ExperimentListResponse
from app.services.memory_service import get_memory_manager

router = APIRouter()


def _parse_experiment(row: dict) -> Experiment:
    created = row.get("created_at") or datetime.now(timezone.utc).isoformat()
    updated = row.get("updated_at") or created
    if isinstance(created, (int, float)):
        created = datetime.fromtimestamp(created, tz=timezone.utc)
    elif isinstance(created, str):
        created = datetime.fromisoformat(created.replace("Z", "+00:00"))
    if isinstance(updated, (int, float)):
        updated = datetime.fromtimestamp(updated, tz=timezone.utc)
    elif isinstance(updated, str):
        updated = datetime.fromisoformat(updated.replace("Z", "+00:00"))
    return Experiment(
        id=int(row["id"]),
        name=row.get("name") or f"Experiment {row['id']}",
        stage=row.get("stage") or "initial",
        created_at=created,
        updated_at=updated,
    )


@router.get("/experiments", response_model=ExperimentListResponse)
def list_experiments(
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> ExperimentListResponse:
    memory = get_memory_manager()
    memory.create_user(user.id, user.email or user.id)
    rows = memory.list_experiments(user.id) or []
    items: List[Experiment] = []
    for row in rows:
        if isinstance(row, dict):
            items.append(_parse_experiment(row))
    return ExperimentListResponse(items=items)


@router.get("/experiments/{experiment_id}", response_model=Experiment)
def get_experiment(
    experiment_id: int,
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> Experiment:
    memory = get_memory_manager()
    row = memory.get_experiment(experiment_id)
    if not row:
        raise HTTPException(status_code=404, detail="Experiment not found")
    if isinstance(row, dict) and row.get("user_id") and row["user_id"] != user.id:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return _parse_experiment(row if isinstance(row, dict) else {"id": experiment_id, "name": "Experiment"})
