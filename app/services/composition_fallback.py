"""Build a composition CSV when uploads omit one (required by curve fitting)."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import List, Optional

from app.tools.demo_data_generator import generate_demo_composition_csv
from app.tools.fitting_agent import infer_wells_from_file_metadata
from app.tools.paths import get_user_data_dir

_WELL_RE = re.compile(r"^[A-H](?:[1-9]|1[0-2])$", re.I)
_R_RE = re.compile(r"^R\d+$", re.I)


def _wells_from_data_csv_header(data_csv_path: str, limit: int = 96) -> List[str]:
    wells: List[str] = []
    seen = set()
    try:
        with open(data_csv_path, encoding="utf-8", errors="ignore") as f:
            for _ in range(80):
                line = f.readline()
                if not line:
                    break
                for part in re.split(r"[,;\t]", line):
                    token = part.strip().strip('"').upper()
                    if not token or token in ("WAVELENGTH", "WL", "PLACEHOLDER", "NAN"):
                        continue
                    if _WELL_RE.match(token) or _R_RE.match(token):
                        if token not in seen:
                            seen.add(token)
                            wells.append(token)
                            if len(wells) >= limit:
                                return wells
    except OSError:
        pass
    return wells


def ensure_composition_csv(data_csv_path: str, composition_csv_path: Optional[str] = None) -> str:
    """
    Return a valid composition CSV path. Generates a placeholder composition beside uploads when missing.
    """
    if composition_csv_path and str(composition_csv_path).strip():
        p = Path(composition_csv_path).expanduser()
        if p.is_file():
            return str(p.resolve())

    wells = infer_wells_from_file_metadata(data_csv_path) or _wells_from_data_csv_header(data_csv_path)
    if not wells:
        wells = [f"A{i}" for i in range(1, 9)]

    out_dir = Path(get_user_data_dir()) / "uploads" / "curve_fitting" / "generated" / uuid.uuid4().hex[:10]
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "composition_auto.csv"
    generate_demo_composition_csv(wells, output_path=str(out_path))
    return str(out_path.resolve())
