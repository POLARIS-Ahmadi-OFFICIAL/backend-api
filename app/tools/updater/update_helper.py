"""
Standalone helper that swaps a staged desktop app into place.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


def _wait_for_pid(pid: int, timeout_seconds: int = 30) -> None:
    """Wait for a PID to exit."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        except PermissionError:
            return
        time.sleep(0.2)


def _write_log(log_path: Path, message: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as log_file:
        log_file.write(message.rstrip() + "\n")


def _remove_path(target: Path) -> None:
    if not target.exists():
        return
    if target.is_dir():
        shutil.rmtree(target, ignore_errors=True)
    else:
        target.unlink(missing_ok=True)


def _launch_updated_app(platform_name: str, install_target: Path, launch_path: Path) -> None:
    if platform_name == "darwin":
        subprocess.Popen(["open", str(install_target)])
        return

    if platform_name == "windows":
        subprocess.Popen(
            [str(launch_path)],
            cwd=str(install_target),
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
        return

    raise RuntimeError(f"Unsupported updater platform: {platform_name}")


def main() -> int:
    if len(sys.argv) < 4:
        return 1

    pending_path = Path(sys.argv[1])
    launcher_pid = int(sys.argv[2])
    log_path = Path(sys.argv[3])

    if not pending_path.exists():
        _write_log(log_path, "Pending update marker missing; nothing to do.")
        return 0

    with open(pending_path, "r", encoding="utf-8") as pending_file:
        data = json.load(pending_file)

    platform_name = data.get("platform", "macos")
    install_target = Path(data["install_target"])
    launch_path = Path(data.get("install_launch_path", install_target))
    staged_path = Path(data.get("staged_path", data.get("staged_bundle_path", "")))
    staging_dir = Path(data["staging_dir"])
    download_path = Path(data["download_path"])
    backup_target = install_target.with_name(f"{install_target.name}.previous")

    _write_log(log_path, f"Waiting for launcher PID {launcher_pid} to exit")
    _wait_for_pid(launcher_pid)

    if not staged_path.exists():
        _write_log(log_path, "Staged install target does not exist; aborting update.")
        return 1

    try:
        _remove_path(backup_target)

        if install_target.exists():
            shutil.move(str(install_target), str(backup_target))

        shutil.move(str(staged_path), str(install_target))
        pending_path.unlink(missing_ok=True)

        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        if download_path.exists():
            download_path.unlink(missing_ok=True)
        _remove_path(backup_target)

        _write_log(log_path, f"Installed update to {install_target}")
        _launch_updated_app(platform_name, install_target, launch_path)
        return 0
    except Exception as exc:
        _write_log(log_path, f"Update helper failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
