from __future__ import annotations

# Node names where the pipeline pauses and waits for frontend confirmation
INTERRUPT_NODES: list[str] = [
    "hypothesis_checkpoint",
    "experiment_checkpoint",
    "curve_fitting_checkpoint",
    "analysis_checkpoint",
]


def build_resume_config(thread_id: str) -> dict:
    """Return the LangGraph config dict needed to resume a paused thread."""
    return {"configurable": {"thread_id": thread_id}}


def build_start_config(thread_id: str) -> dict:
    """Return the LangGraph config dict for starting a new thread."""
    return {"configurable": {"thread_id": thread_id}}
