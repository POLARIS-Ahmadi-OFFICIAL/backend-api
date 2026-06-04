import json
from pathlib import Path

from app.services.curve_fitting_exports import (
    find_latest_curve_fitting_pair,
    materialize_curve_fitting_json,
    resolve_results_path,
    sync_ml_paths_from_curve_fitting,
)


class _Mem:
    def __init__(self):
        self._d = {}

    def get_var(self, k, default=None):
        return self._d.get(k, default)

    def set_var(self, k, v):
        self._d[k] = v


def test_resolve_results_path_strips_prefix(tmp_path, monkeypatch):
    monkeypatch.setenv("POLARIS_RESULTS_DIR", str(tmp_path))
    f = tmp_path / "sample_peak_fit_results.json"
    f.write_text("{}")
    assert resolve_results_path("results/sample_peak_fit_results.json") == f.resolve()


def test_materialize_from_serialized_session(tmp_path, monkeypatch):
    monkeypatch.setenv("POLARIS_RESULTS_DIR", str(tmp_path))
    mem = _Mem()
    mem.set_var(
        "curve_fitting_results",
        {
            "wells": [
                {
                    "well_name": "A1",
                    "read": "1",
                    "fit": {
                        "success": True,
                        "r2": 0.99,
                        "peaks": [{"center": 500.0, "height": 1.0, "fwhm": 10.0}],
                    },
                }
            ],
            "summary": {"total_wells": 1, "successful_fits": 1},
        },
    )
    path = materialize_curve_fitting_json(mem)
    assert path and Path(path).is_file()
    data = json.loads(Path(path).read_text())
    assert "A1" in data["wells"]


def test_sync_finds_nested_results(tmp_path, monkeypatch):
    monkeypatch.setenv("POLARIS_RESULTS_DIR", str(tmp_path))
    demo = tmp_path / "demo"
    demo.mkdir()
    j = demo / "data_peak_fit_results.json"
    j.write_text(json.dumps({"wells": {"A1": {"fitting_results": {"quality_peaks": []}}}}))
    pair = find_latest_curve_fitting_pair()
    assert pair and pair[0] == str(j.resolve())
    mem = _Mem()
    out = sync_ml_paths_from_curve_fitting(mem)
    assert out["json_path"] == str(j.resolve())
