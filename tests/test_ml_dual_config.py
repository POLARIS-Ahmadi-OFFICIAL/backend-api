"""Dual GP column helpers and config merge."""

import pandas as pd

from app.tools.ml_automation import (
    _config_for_dual_gp,
    _config_for_monte_carlo,
    _default_feature_columns,
    _default_performance_column,
    can_compute_instability_from_csv,
    inspect_peak_csv,
)


def test_default_performance_column_r_squared():
    df = pd.DataFrame(
        {
            "R_squared": [0.9, 0.8],
            "Peak_1_Wavelength": [500.0, 510.0],
            "Peak_1_Intensity": [100.0, 90.0],
        }
    )
    numeric = df.select_dtypes(include="number").columns.tolist()
    assert _default_performance_column(df, numeric) == "R_squared"


def test_default_feature_columns_prefers_peaks():
    numeric = ["R_squared", "Peak_1_Wavelength", "Peak_1_Intensity", "Peak_2_Wavelength"]
    feats = _default_feature_columns(numeric, "R_squared", "Peak_1_Intensity")
    assert "Peak_1_Wavelength" in feats
    assert "R_squared" not in feats


def test_config_merge_nested():
    cfg = {
        "dual_gp": {"beta": 3.0},
        "monte_carlo_tree": {"n_attempts": 100},
        "target": "foo",
    }
    dual = _config_for_dual_gp(cfg)
    assert dual["beta"] == 3.0
    assert dual["target"] == "foo"
    mc = _config_for_monte_carlo(cfg)
    assert mc["n_attempts"] == 100


def test_inspect_peak_csv(tmp_path):
    p = tmp_path / "peaks.csv"
    p.write_text(
        "Read,Well,R_squared,Peak_1_Wavelength,Peak_1_Intensity\n"
        "1,A01,0.95,500,100\n"
        "2,A01,0.90,505,95\n"
    )
    meta = inspect_peak_csv(str(p))
    assert meta["ok"] is True
    assert meta["default_performance_target"] == "R_squared"
    assert meta["can_compute_instability"] is True
    assert meta["default_stability_target"] == "Peak_1_Wavelength"
    assert "Peak_1_Intensity" in meta["default_feature_columns"]


def test_can_compute_instability_peak_columns():
    df = pd.DataFrame({"Peak_1_Wavelength": [1], "Peak_1_Intensity": [2]})
    assert can_compute_instability_from_csv(df) is True
