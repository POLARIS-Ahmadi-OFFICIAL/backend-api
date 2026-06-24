from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from app.graph.state import PolarisGraphState
from app.llm.chains.routing import watcher_routing_chain
from app.services.memory_service import get_memory_manager
from app.tools.memory_adapter import MemoryAdapter


async def watcher_node(state: PolarisGraphState, config: RunnableConfig) -> PolarisGraphState:
    memory = get_memory_manager()
    event_description = memory.get_var("last_watcher_event") or "unknown filesystem event"
    try:
        next_agent = await watcher_routing_chain.ainvoke({"event_description": event_description})
        next_agent = next_agent.strip()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Watcher routing chain failed: %s", exc)
        next_agent = "fallback"
    return MemoryAdapter.write(memory, state, current_agent=next_agent)
