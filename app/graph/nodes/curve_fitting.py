from __future__ import annotations

from langgraph.graph import END, StateGraph
from langchain_core.runnables import RunnableConfig

from app.graph.state import PolarisGraphState
from app.services.curve_fitting_service import get_curve_fitting_results
from app.services.memory_service import get_memory_manager
from app.tools.memory_adapter import MemoryAdapter


async def _load_data_node(state: PolarisGraphState, config: RunnableConfig) -> PolarisGraphState:
    memory = get_memory_manager()
    uploaded = memory.get_var("uploaded_files") or []
    return MemoryAdapter.write(
        memory, state,
        current_agent="curve_fitting",
        stage="curve_fitting",
    )


async def _run_fitting_node(state: PolarisGraphState, config: RunnableConfig) -> PolarisGraphState:
    memory = get_memory_manager()
    # Fitting is CPU-bound and already managed by CurveFittingAgent + CurveFittingService
    # The graph delegates: if a fit has already been run (memory has results), use them;
    # otherwise the frontend triggers fitting via the existing /agents/curve-fitting endpoint
    results = get_curve_fitting_results(memory)
    raw = results.get("results") if isinstance(results, dict) else None
    return MemoryAdapter.write(
        memory, state,
        curve_fitting_results=raw,
    )


async def _export_results_node(state: PolarisGraphState, config: RunnableConfig) -> PolarisGraphState:
    memory = get_memory_manager()
    # Export path is already handled by CurveFittingExports service; just advance stage
    return MemoryAdapter.write(memory, state, stage="curve_fitting")


def curve_fitting_subgraph() -> object:
    """Build and compile the 3-node curve fitting sub-graph."""
    g = StateGraph(PolarisGraphState)
    g.add_node("load_data", _load_data_node)
    g.add_node("run_fitting", _run_fitting_node)
    g.add_node("export_results", _export_results_node)
    g.set_entry_point("load_data")
    g.add_edge("load_data", "run_fitting")
    g.add_edge("run_fitting", "export_results")
    g.add_edge("export_results", END)
    return g.compile()
