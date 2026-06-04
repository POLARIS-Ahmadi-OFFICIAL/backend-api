"""Upload experiment artifacts to a Jupyter server (Streamlit parity)."""

from __future__ import annotations

import base64
from typing import Any, Dict, Tuple

import requests

from app.tools.database import DEFAULT_JUPYTER_CONFIG


def get_jupyter_config(memory: Any) -> Dict[str, Any]:
    stored = memory.get_var("jupyter_config")
    if not isinstance(stored, dict):
        return dict(DEFAULT_JUPYTER_CONFIG)
    return {
        "server_url": str(stored.get("server_url") or DEFAULT_JUPYTER_CONFIG["server_url"]),
        "token": str(stored.get("token") or ""),
        "upload_enabled": bool(stored.get("upload_enabled")),
        "notebook_path": str(stored.get("notebook_path") or DEFAULT_JUPYTER_CONFIG["notebook_path"]),
    }


def merge_jupyter_config(memory: Any, patch: Dict[str, Any]) -> Dict[str, Any]:
    current = get_jupyter_config(memory)
    for key in ("server_url", "token", "upload_enabled", "notebook_path"):
        if key in patch and patch[key] is not None:
            if key == "upload_enabled":
                current[key] = bool(patch[key])
            else:
                current[key] = str(patch[key])
    memory.set_var("jupyter_config", current)
    return current


def jupyter_ready(cfg: Dict[str, Any]) -> Tuple[bool, str]:
    if not cfg.get("upload_enabled"):
        return False, "Enable Jupyter upload in Settings."
    if not str(cfg.get("server_url") or "").strip():
        return False, "Set Jupyter server URL in Settings."
    return True, ""


def upload_to_jupyter(
    server_url: str,
    token: str,
    file_content: str,
    filename: str,
    notebook_path: str,
) -> Tuple[bool, str]:
    """Upload a text file via Jupyter contents API."""
    try:
        server_url = str(server_url).rstrip("/")
        if not server_url.startswith("http"):
            server_url = f"http://{server_url}"

        path = f"{notebook_path.strip('/')}/{filename}" if notebook_path else filename
        api_url = f"{server_url}/api/contents/{path}"

        headers: Dict[str, str] = {}
        if token:
            headers["Authorization"] = f"token {token}"

        if filename.endswith((".csv", ".py", ".txt")):
            content_data = {"type": "file", "format": "text", "content": file_content}
        else:
            raw = file_content.encode() if isinstance(file_content, str) else file_content
            content_data = {
                "type": "file",
                "format": "base64",
                "content": base64.b64encode(raw).decode(),
            }

        response = requests.put(api_url, json=content_data, headers=headers, timeout=30)
        if response.status_code in (200, 201):
            return True, f"Successfully uploaded {filename} to {path}"
        return False, f"Failed to upload: {response.status_code} - {response.text}"
    except requests.exceptions.RequestException as exc:
        return False, f"Connection error: {exc}"
    except Exception as exc:
        return False, f"Error uploading file: {exc}"


def upload_with_memory_config(
    memory: Any,
    file_content: str,
    filename: str,
) -> Dict[str, Any]:
    cfg = get_jupyter_config(memory)
    ready, msg = jupyter_ready(cfg)
    if not ready:
        return {"success": False, "message": msg}
    success, message = upload_to_jupyter(
        cfg["server_url"],
        cfg["token"],
        file_content,
        filename,
        cfg["notebook_path"],
    )
    return {
        "success": success,
        "message": message,
        "filename": filename,
        "notebook_path": cfg["notebook_path"],
    }
