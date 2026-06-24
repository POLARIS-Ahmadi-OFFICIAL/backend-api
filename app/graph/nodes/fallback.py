from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from app.graph.state import PolarisGraphState
from app.services.memory_service import get_memory_manager
from app.tools.memory_adapter import MemoryAdapter


async def fallback_node(state: PolarisGraphState, config: RunnableConfig) -> PolarisGraphState:
    memory = get_memory_manager()
    memory.log_event(
        "pipeline_error",
        {"stage": state.get("stage"), "error": state.get("error")},
        mode="graph",
    )
    return MemoryAdapter.write(
        memory, state,
        stage="error",
        current_agent="fallback",
    )
