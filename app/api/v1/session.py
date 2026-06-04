from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.auth import AuthUser
from app.core.deps import get_current_user
from app.services.memory_service import get_memory_manager

router = APIRouter()


@router.post("/session/cache/clear")
def clear_session_cache(
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> dict:
    """Clear agent session state and interaction history; keep LLM/API settings."""
    memory = get_memory_manager()
    memory.clear_session_cache()
    return {"status": "success", "message": "Session cache cleared."}
