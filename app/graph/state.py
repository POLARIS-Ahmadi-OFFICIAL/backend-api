from __future__ import annotations

from typing import Any, Optional
from typing_extensions import TypedDict


class PolarisGraphState(TypedDict):
    # Pipeline stage
    stage: str  # "initial"|"hypothesis"|"experiment"|"curve_fitting"|"ml_models"|"analysis"|"complete"|"error"

    # Domain object presence flags (written by MemoryAdapter)
    has_hypothesis: bool
    has_experimental_outputs: bool
    has_curve_results: bool
    has_ml_results: bool
    has_analysis_results: bool
    hypothesis_ready: bool

    # Thin previews for edge conditions and frontend display (<=500 chars)
    hypothesis_preview: Optional[str]
    research_goal: Optional[str]

    # Execution context
    experiment_id: Optional[int]
    current_agent: Optional[str]
    error: Optional[str]
    interrupt_payload: Optional[dict[str, Any]]  # surfaced to frontend at checkpoints

    # Routing config
    routing_mode: str  # "autonomous" | "manual"
    manual_workflow: list[str]
    workflow_index: int
