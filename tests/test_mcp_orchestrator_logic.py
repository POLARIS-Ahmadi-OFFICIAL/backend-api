from __future__ import annotations

from app.watcher.orchestrator_mcp import OrchestratorService, SearchPapersRequest


class _FakeMemory:
    def __init__(self):
        self._vars = {
            "mcp_literature_config": {
                "endpoint": "http://127.0.0.1:8000/mcp",
                "manual_manifest_path": "data/manual_papers_manifest.json",
            }
        }
        self._negative = [
            {"hypothesis_text": "Use material X with additive Y for stability", "status": "rejected"}
        ]
        self._outcomes = [
            {
                "hypothesis_text": "Material Z in ETL improved fill factor",
                "status": "positive",
                "material_hint": "Material Z",
                "source": "lab",
            }
        ]
        self.recorded = []

    def init_session(self):
        return None

    def get_var(self, name: str, default=None):
        return self._vars.get(name, default)

    def get_negative_hypotheses(self, limit=None):
        return self._negative

    def get_hypothesis_outcomes(self, limit=200):
        return self._outcomes

    def add_hypothesis_outcome(self, **kwargs):
        self.recorded.append(kwargs)

    def add_negative_hypothesis(self, **kwargs):
        self.recorded.append(kwargs)


def test_history_gate_blocks_similar_negative():
    svc = OrchestratorService(memory=_FakeMemory())
    gate = svc._history_guard("Use material X with additive Y for long-term stability")
    assert gate["blocked"] is True
    assert gate["reasons"]


def test_history_gate_allows_and_surfaces_positive_precedent():
    svc = OrchestratorService(memory=_FakeMemory())
    gate = svc._history_guard("Try a new architecture", material_hint="Material Z")
    assert gate["blocked"] is False
    assert gate["positive_precedents"]


def test_search_request_schema_defaults():
    req = SearchPapersRequest(query="perovskite")
    assert req.source_mode == "hybrid"
