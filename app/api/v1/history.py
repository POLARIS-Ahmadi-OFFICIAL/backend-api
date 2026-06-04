from datetime import datetime, timezone
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, Query

from app.core.auth import AuthUser
from app.core.deps import get_current_user
from app.schemas.api_models import HistoryEntry, HistoryListResponse
from app.services.memory_service import get_memory_manager

router = APIRouter()

_AGENT_ALIASES = {
    "all": None,
    "all interactions": None,
    "hypothesis": "hypothesis",
    "experiment": "experiment",
    "curve_fitting": "curve_fitting",
    "curve fitting": "curve_fitting",
    "ml_models": "ml_models",
    "ml models": "ml_models",
    "analysis": "analysis",
    "general": "general",
}


def _normalize_agent_filter(agent: Optional[str]) -> Optional[str]:
    if not agent:
        return None
    key = agent.strip().lower().replace("-", "_")
    return _AGENT_ALIASES.get(key, key.replace(" ", "_"))


def _parse_timestamp(ts) -> datetime:
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    if isinstance(ts, str):
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return datetime.now(timezone.utc)


def _mode_matches(mode: Optional[str], agent_filter: Optional[str]) -> bool:
    if agent_filter is None:
        return True
    if not mode:
        return agent_filter == "general"
    normalized = mode.strip().lower().replace(" ", "_").replace("-", "_")
    return normalized == agent_filter


@router.get("/history", response_model=HistoryListResponse)
def get_history(
    user: Annotated[AuthUser, Depends(get_current_user)],
    experiment_id: Annotated[Optional[int], Query()] = None,
    agent: Annotated[Optional[str], Query()] = None,
    limit: Annotated[int, Query(le=500)] = 200,
) -> HistoryListResponse:
    memory = get_memory_manager()
    agent_filter = _normalize_agent_filter(agent)
    exp_id = experiment_id
    if exp_id is None:
        raw = memory.get_var("current_experiment_id") or 0
        exp_id = int(raw) if raw else None

    items: List[HistoryEntry] = []
    seen: set[str] = set()

    def add_entry(
        entry_id: str,
        ts,
        event_type: str,
        mode: Optional[str],
        payload: dict,
        source: str,
    ) -> None:
        if entry_id in seen:
            return
        if not _mode_matches(mode, agent_filter):
            return
        seen.add(entry_id)
        role = payload.get("role")
        component = payload.get("component")
        summary = (
            payload.get("message")
            or payload.get("hypothesis")
            or payload.get("question")
            or payload.get("thoughts")
        )
        if isinstance(summary, list):
            summary = "; ".join(str(s) for s in summary[:3])
        if summary is not None and not isinstance(summary, str):
            summary = str(summary)
        items.append(
            HistoryEntry(
                id=entry_id,
                timestamp=_parse_timestamp(ts),
                event_type=event_type,
                agent=mode or "general",
                component=component,
                role=role,
                summary=(summary[:2000] if summary else None),
                experiment_id=exp_id,
            )
        )

    events = memory._db.get_conversation_events(exp_id) if hasattr(memory, "_db") else []
    for idx, event in enumerate(events):
        event_type = event.get("type", "event")
        if event_type not in ("interaction", "history"):
            continue
        mode = event.get("mode") or "general"
        payload = event.get("payload") or {}
        ts = event.get("timestamp")
        add_entry(f"evt-{idx}", ts, event_type, mode, payload, "events")

    for idx, row in enumerate(memory.get_var("interactions", []) or []):
        mode = row.get("mode") or "general"
        if row.get("role") or row.get("message"):
            payload = {
                "role": row.get("role"),
                "message": row.get("message"),
                "component": row.get("component"),
            }
            ts = row.get("timestamp")
            add_entry(f"legacy-{idx}", ts, "interaction", mode, payload, "legacy")

    items.sort(key=lambda e: e.timestamp, reverse=True)
    return HistoryListResponse(items=items[:limit])
