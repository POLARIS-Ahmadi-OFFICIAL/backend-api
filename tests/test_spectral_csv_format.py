"""Parse Cytation-style spectral CSV (Read 1:EM Spectrum + Wavelength + wells)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.tools.demo_data_generator import generate_demo_composition_csv
from app.tools.fitting_agent import CurveFitting, build_agent_config


SAMPLE_COMMA = """Read 1:EM Spectrum
Wavelength,A1,A2,A3
400,0.1,0.05,0.08
410,0.2,0.1,0.15
420,0.8,0.4,0.6
430,2.1,1.0,1.5
440,3.2,1.6,2.4
450,4.1,2.0,3.0
460,3.8,1.9,2.8
470,2.9,1.4,2.1
480,1.8,0.9,1.3
490,0.9,0.4,0.7
500,0.3,0.15,0.25
"""

SAMPLE_TAB = SAMPLE_COMMA.replace(",", "\t")


@pytest.mark.parametrize("content", [SAMPLE_COMMA, SAMPLE_TAB])
def test_parse_read1_em_spectrum_format(content: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        data_path = Path(tmp) / "spectral.csv"
        comp_path = Path(tmp) / "composition.csv"
        data_path.write_text(content, encoding="utf-8")
        generate_demo_composition_csv(["A1", "A2", "A3"], output_path=str(comp_path))

        raw, _ = CurveFitting.load_csvs(str(data_path), str(comp_path))
        blocks = CurveFitting.parse_all_reads(raw)

        assert 1 in blocks
        block = blocks[1]
        assert "Wavelength" in block.columns
        assert set(block.columns) >= {"Wavelength", "A1", "A2", "A3"}
        assert len(block) == 11
        assert float(block.loc[block.index[0], "Wavelength"]) == 400.0
        assert float(block.loc[block.index[0], "A1"]) == pytest.approx(0.1)

        agent = CurveFitting.__new__(CurveFitting)
        cfg = build_agent_config(
            data_csv=str(data_path),
            composition_csv=str(comp_path),
            read_selection="all",
        )
        agent.cfg = cfg
        curated = agent.curate_dataset()
        assert "A1" in curated["wells"]
        assert "A2" in curated["wells"]
        assert "A3" in curated["wells"]
        assert 1 in curated["reads"]
