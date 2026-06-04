"""Convert numpy/lmfit objects to JSON-serializable Python types."""

from __future__ import annotations

from typing import Any

import numpy as np


def to_jsonable(obj: Any) -> Any:
    """Recursively convert values for json.dumps / FastAPI responses."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (np.floating, np.integer, np.bool_)):
        return obj.item()
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_jsonable(v) for v in obj]
    if hasattr(obj, "model_dump"):
        return to_jsonable(obj.model_dump())
    if hasattr(obj, "__dict__") and not isinstance(obj, type):
        return to_jsonable(vars(obj))
    return str(obj)
