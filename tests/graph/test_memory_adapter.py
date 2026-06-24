from unittest.mock import MagicMock
from app.graph.state import PolarisGraphState
from app.tools.memory_adapter import MemoryAdapter


def _base_state() -> PolarisGraphState:
    return {
        "stage": "hypothesis",
        "has_hypothesis": False,
        "has_experimental_outputs": False,
        "has_curve_results": False,
        "has_ml_results": False,
        "has_analysis_results": False,
        "hypothesis_ready": False,
        "hypothesis_preview": None,
        "research_goal": None,
        "experiment_id": None,
        "current_agent": None,
        "error": None,
        "interrupt_payload": None,
        "routing_mode": "autonomous",
        "manual_workflow": [],
        "workflow_index": 0,
    }


def test_write_stores_in_memory_manager():
    memory = MagicMock()
    state = _base_state()
    result = MemoryAdapter.write(memory, state, research_goal="Why does GaN glow?")
    memory.set_var.assert_called_with("research_goal", "Why does GaN glow?")
    assert result["research_goal"] == "Why does GaN glow?"


def test_write_sets_has_hypothesis_flag():
    memory = MagicMock()
    state = _base_state()
    result = MemoryAdapter.write(memory, state, hypothesis="A long hypothesis text")
    assert result["has_hypothesis"] is True
    assert result["hypothesis_preview"] == "A long hypothesis text"


def test_write_truncates_preview_to_500():
    memory = MagicMock()
    state = _base_state()
    long_text = "x" * 600
    result = MemoryAdapter.write(memory, state, hypothesis=long_text)
    assert len(result["hypothesis_preview"]) == 500


def test_write_sets_curve_results_flag():
    memory = MagicMock()
    state = _base_state()
    result = MemoryAdapter.write(memory, state, curve_fitting_results={"peaks": []})
    assert result["has_curve_results"] is True


def test_write_sets_ml_results_flag():
    memory = MagicMock()
    state = _base_state()
    result = MemoryAdapter.write(memory, state, gp_results={"model": "GP"})
    assert result["has_ml_results"] is True


def test_write_preserves_unrelated_state_fields():
    memory = MagicMock()
    state = _base_state()
    state["stage"] = "analysis"
    state["workflow_index"] = 3
    result = MemoryAdapter.write(memory, state, error=None)
    assert result["stage"] == "analysis"
    assert result["workflow_index"] == 3


def test_write_clears_flag_when_value_is_none():
    memory = MagicMock()
    state = _base_state()
    state["has_curve_results"] = True
    result = MemoryAdapter.write(memory, state, curve_fitting_results=None)
    assert result["has_curve_results"] is False
