from __future__ import annotations

import logging

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt
from langchain_core.runnables import RunnableConfig

from app.graph.state import PolarisGraphState
from app.services.hypothesis_chat import submit_question
from app.services.memory_service import get_memory_manager
from app.tools.memory_adapter import MemoryAdapter

_logger = logging.getLogger(__name__)


async def _clarify_node(state: PolarisGraphState, config: RunnableConfig) -> PolarisGraphState:
    memory = get_memory_manager()
    question = state.get("research_goal") or memory.get_var("research_goal") or ""  # noqa: F841
    return MemoryAdapter.write(memory, state, current_agent="hypothesis", stage="hypothesis")


async def _socratic_node(state: PolarisGraphState, config: RunnableConfig) -> PolarisGraphState:
    memory = get_memory_manager()
    question = state.get("research_goal") or memory.get_var("research_goal") or ""
    try:
        # Delegates to existing hypothesis_chat service which handles the full socratic + ToT pipeline
        result = submit_question(memory, question)  # noqa: F841
        hyp = memory.view_component("hypothesis")  # noqa: F841
    except Exception as exc:
        _logger.warning("Hypothesis submit_question failed in graph node: %s", exc)
        result = {}  # noqa: F841
        hyp = None  # noqa: F841
    options = [
        memory.view_component("next_step_option_1"),
        memory.view_component("next_step_option_2"),
        memory.view_component("next_step_option_3"),
    ]
    return MemoryAdapter.write(
        memory, state,
        interrupt_payload={
            "stage": "hypothesis",
            "options": [o for o in options if o],
            "hint": "Select one of the hypothesis options to continue.",
        },
    )


async def _tot_interrupt_node(state: PolarisGraphState, config: RunnableConfig) -> PolarisGraphState:
    # Pause here — frontend must POST /pipeline/resume with {"choice_index": 0|1|2}
    payload = state.get("interrupt_payload") or {}
    decision = interrupt(payload)  # suspends graph; LangGraph handles the pause
    memory = get_memory_manager()
    choice_index = int(decision.get("choice_index", 0)) if isinstance(decision, dict) else 0
    memory.set_var("chosen_option_index", choice_index)
    return {**state, "interrupt_payload": None}


async def _deepen_node(state: PolarisGraphState, config: RunnableConfig) -> PolarisGraphState:
    memory = get_memory_manager()
    # Deepening is handled inside hypothesis_chat.choose_option
    from app.services.hypothesis_chat import choose_option
    choice_index = int(memory.get_var("chosen_option_index") or 0)
    # choose_option expects a string "1", "2", or "3" (1-based)
    choice_str = str(choice_index + 1)
    if choice_str not in ("1", "2", "3"):
        choice_str = "1"
    try:
        choose_option(memory, choice_str)
    except Exception as exc:
        _logger.warning("choose_option failed in graph node: %s", exc)
    return {**state}


async def _synthesis_node(state: PolarisGraphState, config: RunnableConfig) -> PolarisGraphState:
    memory = get_memory_manager()
    hypothesis = memory.view_component("hypothesis")
    return MemoryAdapter.write(
        memory, state,
        hypothesis=hypothesis,
        hypothesis_ready=True,
        stage="hypothesis",
        interrupt_payload={
            "stage": "hypothesis",
            "hypothesis_preview": (str(hypothesis)[:500] if hypothesis else ""),
            "hint": "Review the synthesized hypothesis before proceeding to experiment design.",
        },
    )


async def _hypothesis_checkpoint_node(state: PolarisGraphState, config: RunnableConfig) -> PolarisGraphState:
    payload = state.get("interrupt_payload") or {}
    interrupt(payload)  # pause — frontend reviews hypothesis
    return {**state, "interrupt_payload": None}


def hypothesis_subgraph() -> CompiledStateGraph:
    g = StateGraph(PolarisGraphState)
    g.add_node("clarify", _clarify_node)
    g.add_node("socratic", _socratic_node)
    g.add_node("tot_interrupt", _tot_interrupt_node)
    g.add_node("deepen", _deepen_node)
    g.add_node("synthesis", _synthesis_node)
    g.add_node("hypothesis_checkpoint", _hypothesis_checkpoint_node)
    g.set_entry_point("clarify")
    g.add_edge("clarify", "socratic")
    g.add_edge("socratic", "tot_interrupt")
    g.add_edge("tot_interrupt", "deepen")
    g.add_edge("deepen", "synthesis")
    g.add_edge("synthesis", "hypothesis_checkpoint")
    g.add_edge("hypothesis_checkpoint", END)
    return g.compile()
