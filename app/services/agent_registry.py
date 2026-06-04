from typing import Any, List, Optional

from app.agents.router import AgentRouter


def build_agent_router() -> AgentRouter:
    from app.agents.analysis_agent import AnalysisAgent
    from app.agents.curve_fitting_agent import CurveFittingAgent
    from app.agents.experiment_agent import ExperimentAgent
    from app.agents.fallback_agent import FallbackAgent
    from app.agents.hypothesis_agent import HypothesisAgent
    from app.agents.ml_models_agent import MLModelsAgent
    from app.agents.watcher_agent import WatcherAgent

    agents: List[Any] = [
        HypothesisAgent(name="Hypothesis Agent", desc="API", question=""),
        ExperimentAgent(name="Experiment Agent", desc="API", params_const={}),
        CurveFittingAgent(),
        AnalysisAgent(),
        MLModelsAgent(),
        WatcherAgent(),
    ]
    return AgentRouter(agents=agents, fallback_agent=FallbackAgent())


_AGENT_ALIASES = {
    "hypothesis": "Hypothesis Agent",
    "experiment": "Experiment Agent",
    "curve-fitting": "Curve Fitting Agent",
    "curve fitting": "Curve Fitting Agent",
    "ml": "ML Models",
    "ml models": "ML Models",
    "analysis": "Analysis Agent",
    "watcher": "Watcher Agent",
}


def resolve_agent_by_name(name: str) -> Optional[Any]:
    router = build_agent_router()
    key = (name or "").strip().lower()
    canonical = _AGENT_ALIASES.get(key, name)
    found = router._find_agent_by_name(canonical)
    if found:
        return found
    return router._find_agent_by_name(name)
