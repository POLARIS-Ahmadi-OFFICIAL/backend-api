from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class SessionContext:
    """Headless session snapshot passed to agents and the router."""

    experiment_id: Optional[int] = None
    user_id: str = ""
    stage: str = "initial"
    routing_mode: str = "autonomous"
    has_hypothesis: bool = False
    has_experimental_outputs: bool = False
    has_curve_fitting_results: bool = False
    has_analysis_results: bool = False
    has_gp_results: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_router_payload(self, base: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = dict(base or {})
        payload["session_context"] = {
            "experiment_id": self.experiment_id,
            "stage": self.stage,
            "has_hypothesis": self.has_hypothesis,
            "has_experimental_outputs": self.has_experimental_outputs,
            "has_curve_fitting_results": self.has_curve_fitting_results,
            "has_analysis_results": self.has_analysis_results,
            "has_gp_results": self.has_gp_results,
            "hypothesis_preview": self.extra.get("hypothesis_preview"),
        }
        return payload

    @classmethod
    def from_memory(cls, memory: Any, experiment_id: Optional[int] = None) -> "SessionContext":
        exp_id = experiment_id or memory.get_var("current_experiment_id") or 0
        return cls(
            experiment_id=int(exp_id) if exp_id else None,
            user_id=str(memory.get_var("current_user_id") or ""),
            stage=str(memory.get_var("stage") or "initial"),
            routing_mode=str(memory.get_var("routing_mode") or "Autonomous (LLM)"),
            has_hypothesis=bool(memory.get_var("last_hypothesis")),
            has_experimental_outputs=bool(memory.get_var("experimental_outputs")),
            has_curve_fitting_results=bool(memory.get_var("curve_fitting_results")),
            has_analysis_results=bool(memory.get_var("analysis_results")),
            has_gp_results=bool(memory.get_var("gp_results")),
            extra={
                "hypothesis_preview": (memory.get_var("last_hypothesis") or "")[:500] or None,
            },
        )
