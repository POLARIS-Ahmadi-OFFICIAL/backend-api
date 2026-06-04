from pathlib import Path

from app.services.curve_fitting_service import (
    _discover_plot_on_disk,
    _enrich_wells_plot_urls,
    _plot_api_url,
    _resolve_data_path,
)


def test_plot_api_url_includes_read():
    assert _plot_api_url("A1", "1") == "/agents/curve-fitting/plot?well=A1&read=1"


def test_enrich_wells_plot_urls_from_plot_path():
    wells = _enrich_wells_plot_urls(
        [{"well_name": "A1", "read": "1", "plot_path": "results/fit_results_A1_read1.png"}]
    )
    assert wells[0]["plot_url"] == "/agents/curve-fitting/plot?well=A1&read=1"


def test_discover_plot_on_disk(tmp_path, monkeypatch):
    results = tmp_path / "results"
    results.mkdir()
    png = results / "fit_results_B2.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n")
    monkeypatch.chdir(tmp_path)
    assert _discover_plot_on_disk("B2", None) == png.resolve()
    assert _resolve_data_path("results/fit_results_B2.png") == png.resolve()
