"""Experiment session helpers."""

from app.services.experiment_service import patch_manual_inputs


class _Mem:
    def __init__(self) -> None:
        self._data: dict = {}

    def get_var(self, key: str):
        return self._data.get(key)

    def set_var(self, key: str, value) -> None:
        self._data[key] = value


def test_patch_manual_inputs_passes_memory():
    mem = _Mem()
    patch_manual_inputs(mem, {"manual_hypothesis": "H1", "manual_thoughts": "T1"})
    assert mem.get_var("manual_hypothesis") == "H1"
    assert mem.get_var("manual_thoughts") == "T1"
