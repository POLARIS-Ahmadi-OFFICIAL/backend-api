from __future__ import annotations

import asyncio

from langchain_core.runnables import RunnableConfig

from app.agents.ml_models_agent import MLModelsAgent
from app.graph.state import PolarisGraphState
from app.services.memory_service import get_memory_manager
from app.tools.memory_adapter import MemoryAdapter


async def ml_models_node(state: PolarisGraphState, config: RunnableConfig) -> PolarisGraphState:
    memory = get_memory_manager()
    agent = MLModelsAgent("ML Models Agent")
    agent.memory = memory
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, agent.run_agent, memory)
    gp_results = memory.get_var("gp_results") or result.get("gp_results")
    return MemoryAdapter.write(
        memory, state,
        gp_results=gp_results,
        current_agent="ml_models",
        stage="ml_models",
    )
