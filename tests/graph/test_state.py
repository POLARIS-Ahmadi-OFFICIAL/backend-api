from app.graph.state import PolarisGraphState


def test_state_has_required_keys():
    state: PolarisGraphState = {
        "stage": "initial",
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
    assert state["stage"] == "initial"
    assert state["routing_mode"] == "autonomous"
    assert state["workflow_index"] == 0


def test_state_partial_update():
    base: PolarisGraphState = {
        "stage": "hypothesis",
        "has_hypothesis": False,
        "has_experimental_outputs": False,
        "has_curve_results": False,
        "has_ml_results": False,
        "has_analysis_results": False,
        "hypothesis_ready": False,
        "hypothesis_preview": None,
        "research_goal": "test goal",
        "experiment_id": None,
        "current_agent": None,
        "error": None,
        "interrupt_payload": None,
        "routing_mode": "autonomous",
        "manual_workflow": [],
        "workflow_index": 0,
    }
    updated = {**base, "has_hypothesis": True, "hypothesis_preview": "Short preview"}
    assert updated["has_hypothesis"] is True
    assert updated["hypothesis_preview"] == "Short preview"
    assert updated["stage"] == "hypothesis"
