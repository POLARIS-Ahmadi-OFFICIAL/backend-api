"""Workflow sync and agent name resolution."""

from app.services.workflow_followups import (
    resolve_agent_name,
    should_auto_run_ml_after_curve_fitting,
    sync_workflow_from_steps,
)


class _Mem:
    def __init__(self) -> None:
        self._data: dict = {}

    def get_var(self, key: str, default=None):
        return self._data.get(key, default)

    def set_var(self, key: str, value) -> None:
        self._data[key] = value


def test_resolve_agent_name_curve_fitting():
    assert resolve_agent_name("Curve Fitting") == "Curve Fitting Agent"


def test_sync_workflow_from_steps_sets_manual_and_flags():
    mem = _Mem()
    sync_workflow_from_steps(
        mem,
        [
            {"name": "Curve Fitting", "automatic": False},
            {"name": "ML Models", "automatic": True},
            {"name": "Analysis Agent", "automatic": True},
        ],
    )
    assert mem.get_var("manual_workflow") == [
        "Curve Fitting",
        "ML Models",
        "Analysis Agent",
    ]
    assert mem.get_var("workflow_auto_flags") == {
        "Curve Fitting": False,
        "ML Models": True,
        "Analysis Agent": True,
    }
    assert mem.get_var("auto_ml_after_curve_fitting") is True
    assert mem.get_var("auto_route_to_analysis") is True


def test_should_auto_run_ml_from_workflow_order():
    mem = _Mem()
    mem.set_var("manual_workflow", ["Curve Fitting", "ML Models"])
    mem.set_var("workflow_auto_flags", {"ML Models": True})
    mem.set_var("auto_ml_after_curve_fitting", False)
    assert should_auto_run_ml_after_curve_fitting(mem) is True
