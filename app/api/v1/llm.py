from fastapi import APIRouter

from app.core.llm_config import list_providers

router = APIRouter()


@router.get("/llm/providers")
def get_llm_providers():
    """Public metadata for settings UI (models per provider)."""
    return {"providers": list_providers()}
