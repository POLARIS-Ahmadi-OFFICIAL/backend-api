from __future__ import annotations

from typing import Any, Optional, Tuple

from app.graph.state import PolarisGraphState
from app.tools.memory import MemoryManager

# Maps a MemoryManager key to (graph_flag_field, graph_preview_field | None)
_SIGNAL_MAP: dict[str, Tuple[str, Optional[str]]] = {
    "hypothesis":             ("has_hypothesis", "hypothesis_preview"),
    "experimental_outputs":   ("has_experimental_outputs", None),
    "curve_fitting_results":  ("has_curve_results", None),
    "gp_results":             ("has_ml_results", None),
    "analysis_results":       ("has_analysis_results", None),
}


class MemoryAdapter:
    """Dual-write utility: persists values to MemoryManager and syncs routing signals into PolarisGraphState."""

    @staticmethod
    def write(
        memory: MemoryManager,
        state: PolarisGraphState,
        **kwargs: Any,
    ) -> PolarisGraphState:
        """
        For each kwarg:
        - Calls memory.set_var(key, value)
        - If the key is in _SIGNAL_MAP, updates the corresponding bool flag (and preview field) in state
        Returns a new state dict with the updates applied (original state is not mutated).
        """
        updates: dict[str, Any] = {}
        for key, value in kwargs.items():
            memory.set_var(key, value)
            if key in _SIGNAL_MAP:
                flag_field, preview_field = _SIGNAL_MAP[key]
                updates[flag_field] = bool(value)
                if preview_field is not None:
                    if value is not None:
                        updates[preview_field] = str(value)[:500]
                    else:
                        updates[preview_field] = None
            else:
                # Pass-through: unknown key written to memory + forwarded to state if it's a state field
                updates[key] = value
        return {**state, **updates}
