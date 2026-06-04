"""In-process watcher lifecycle for API control (full server in app.watcher.server)."""

from __future__ import annotations

import threading
from typing import Optional

from app.schemas.api_models import WatcherStatus

_state = {
    "running": False,
    "directory": "",
    "port": None,
    "pid": None,
    "message": "Watcher idle",
    "thread": None,
}


def start(*, directory: str, port: int, results_dir: Optional[str] = None) -> WatcherStatus:
    if _state["running"]:
        return status()
    _state["running"] = True
    _state["directory"] = directory
    _state["port"] = port
    _state["message"] = "Watcher registered (use dedicated watcher process for filesystem events)"
    return status()


def stop() -> WatcherStatus:
    _state["running"] = False
    _state["message"] = "Watcher stopped"
    thread: Optional[threading.Thread] = _state.get("thread")
    if thread and thread.is_alive():
        pass
    _state["thread"] = None
    return status()


def status() -> WatcherStatus:
    return WatcherStatus(
        running=_state["running"],
        directory=_state["directory"] or None,
        port=_state["port"],
        pid=_state["pid"],
        message=_state["message"],
    )
