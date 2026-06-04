"""Persist curve-fitting uploads from API clients."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Optional, Tuple

from fastapi import UploadFile

from app.tools.paths import get_user_data_dir

_UPLOAD_SUBDIR = "uploads/curve_fitting"
_SAFE_NAME = re.compile(r"[^a-zA-Z0-9._-]+")


def _uploads_root() -> Path:
    root = Path(get_user_data_dir()) / _UPLOAD_SUBDIR
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_filename(name: Optional[str], fallback: str) -> str:
    raw = (name or fallback).strip() or fallback
    base = Path(raw).name
    cleaned = _SAFE_NAME.sub("_", base)
    return cleaned[:200] or fallback


async def save_upload_file(upload: UploadFile, *, prefix: str = "file") -> str:
    """Write an uploaded file to disk and return its absolute path."""
    session_dir = _uploads_root() / uuid.uuid4().hex[:12]
    session_dir.mkdir(parents=True, exist_ok=True)
    filename = _safe_filename(upload.filename, f"{prefix}.csv")
    dest = session_dir / filename
    content = await upload.read()
    dest.write_bytes(content)
    await upload.close()
    return str(dest.resolve())


async def persist_curve_fitting_uploads(
    data_file: Optional[UploadFile],
    composition_file: Optional[UploadFile],
    *,
    data_file_path: Optional[str] = None,
    composition_file_path: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Resolve data/composition paths from uploads or explicit server paths.
    Raises ValueError if no data source is provided.
    """
    data_path: Optional[str] = None
    comp_path: Optional[str] = None

    if data_file and data_file.filename:
        data_path = await save_upload_file(data_file, prefix="data")
    elif data_file_path and str(data_file_path).strip():
        p = Path(str(data_file_path).strip()).expanduser()
        if not p.is_file():
            raise ValueError(f"Data file not found on server: {p}")
        data_path = str(p.resolve())

    if composition_file and composition_file.filename:
        comp_path = await save_upload_file(composition_file, prefix="composition")
    elif composition_file_path and str(composition_file_path).strip():
        p = Path(str(composition_file_path).strip()).expanduser()
        if not p.is_file():
            raise ValueError(f"Composition file not found on server: {p}")
        comp_path = str(p.resolve())

    if not data_path:
        raise ValueError("A data file is required (upload CSV or provide data_file_path).")

    return data_path, comp_path
