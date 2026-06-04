"""Defaults and option lists for the Experiment agent (Streamlit parity)."""

from __future__ import annotations

from typing import Any, Dict, List

TECHNIQUE_OPTIONS = [
    "in-situ PL",
    "spin coating",
    "absorbance spectroscopy",
    "XRD",
    "SEM",
    "TEM",
    "UV-Vis",
    "photoluminescence",
    "time-resolved PL",
    "impedance spectroscopy",
]

EQUIPMENT_OPTIONS = [
    "spin bot",
    "pipetting robot",
    "glove box",
    "solar simulator",
    "spectrometer",
    "microscope",
    "thermal evaporator",
    "spin coater",
    "Tecan liquid handler",
    "Opentrons liquid handler",
]

INSTRUMENT_OPTIONS = ["Tecan", "Opentrons", "manual pipettes", "multichannel pipettes"]

PLATE_FORMAT_OPTIONS = ["96-well", "384-well", "24-well"]

PARAMETER_OPTIONS = [
    "spin speed",
    "concentration",
    "temperature",
    "humidity",
    "annealing time",
    "layer thickness",
    "mixing ratio",
    "deposition rate",
]

FOCUS_AREA_OPTIONS = [
    "device performance",
    "material stability",
    "process optimization",
    "characterization",
    "scaling",
    "cost reduction",
]

PRESET_MATERIALS = ["Cs", "BDA", "BDA_2", "5AVA", "FAPbI3", "Material 1", "Material 2", "Material 3"]

DEFAULT_CSV_PATH = "/var/lib/jupyter/notebooks/Dual GP 5AVA BDA/"


def default_experimental_constraints() -> Dict[str, Any]:
    return {
        "techniques": [],
        "equipment": [],
        "parameters": [],
        "focus_areas": [],
        "liquid_handling": {
            "instruments": [],
            "plate_format": "96-well",
            "max_volume_per_mixture": 50,
            "materials": [],
            "csv_path": DEFAULT_CSV_PATH,
        },
    }


def merge_constraints(stored: Any) -> Dict[str, Any]:
    base = default_experimental_constraints()
    if not isinstance(stored, dict):
        return base
    lh = stored.get("liquid_handling") if isinstance(stored.get("liquid_handling"), dict) else {}
    base["techniques"] = list(stored.get("techniques") or [])
    base["equipment"] = list(stored.get("equipment") or [])
    base["parameters"] = list(stored.get("parameters") or [])
    base["focus_areas"] = list(stored.get("focus_areas") or [])
    base["liquid_handling"] = {
        **base["liquid_handling"],
        "instruments": list(dict.fromkeys(lh.get("instruments") or [])),
        "plate_format": lh.get("plate_format") or base["liquid_handling"]["plate_format"],
        "max_volume_per_mixture": int(lh.get("max_volume_per_mixture") or 50),
        "materials": list(dict.fromkeys(lh.get("materials") or [])),
        "csv_path": lh.get("csv_path") or DEFAULT_CSV_PATH,
    }
    return base
