from __future__ import annotations

import logging
from typing import Optional

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.checkpoint.base import BaseCheckpointSaver

from app.graph.checkpointer import get_checkpointer
# INTERRUPT_NODES documents which sub-graph nodes pause — sub-graphs call interrupt() internally
# from app.graph.interrupts import INTERRUPT_NODES
from app.graph.nodes.analysis import analysis_subgraph
from app.graph.nodes.curve_fitting import curve_fitting_subgraph
from app.graph.nodes.experiment import experiment_subgraph
from app.graph.nodes.fallback import fallback_node
from app.graph.nodes.hypothesis import hypothesis_subgraph
from app.graph.nodes.ml_models import ml_models_node
from app.graph.nodes.watcher import watcher_node
from app.graph.state import PolarisGraphState
from app.services.memory_service import get_memory_manager

_logger = logging.getLogger(__name__)
_pipeline = None


def _route_after_analysis(state: PolarisGraphState) -> str:
    memory = get_memory_manager()
    verdict = memory.get_var("analysis_verdict") or "complete"
    if verdict == "needs_more_experiments":
        return "experiment"
    return END


def build_pipeline(checkpointer: Optional[BaseCheckpointSaver] = None) -> CompiledStateGraph:
    """Build and compile the top-level POLARIS pipeline StateGraph."""
    g = StateGraph(PolarisGraphState)

    # Embed compiled sub-graphs as single nodes
    g.add_node("hypothesis", hypothesis_subgraph())
    g.add_node("experiment", experiment_subgraph())
    g.add_node("curve_fitting", curve_fitting_subgraph())
    g.add_node("ml_models", ml_models_node)
    g.add_node("analysis", analysis_subgraph())
    g.add_node("fallback", fallback_node)
    g.add_node("watcher", watcher_node)

    g.set_entry_point("hypothesis")
    g.add_edge("hypothesis", "experiment")
    g.add_edge("experiment", "curve_fitting")
    g.add_edge("curve_fitting", "ml_models")
    g.add_edge("ml_models", "analysis")
    g.add_conditional_edges(
        "analysis",
        _route_after_analysis,
        {"experiment": "experiment", END: END},
    )
    g.add_edge("fallback", END)
    g.add_edge("watcher", END)

    cp = checkpointer or get_checkpointer()
    # INTERRUPT_NODES are sub-graph internal node names; sub-graphs use interrupt() calls
    # internally so they pause regardless. We compile without top-level interrupt_before to
    # avoid validation errors since those node names don't exist at the top-level graph scope.
    return g.compile(checkpointer=cp)


def get_pipeline() -> CompiledStateGraph:
    """Singleton accessor for the production pipeline (uses AsyncSqliteSaver)."""
    global _pipeline
    if _pipeline is None:
        _pipeline = build_pipeline()
    return _pipeline
