"""
GitHub Releases updater support for packaged desktop builds.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import shutil
import sys
import urllib.request
import zipfile

from app.tools.paths import (
    get_current_install_target_path,
    get_current_launch_path,
    get_resource_path,
    get_update_download_path,
    get_update_pending_path,
    get_update_staging_dir,
    get_updater_log_path,
)

from .version import (
    APP_VERSION,
    DEFAULT_MACOS_ASSET_NAME,
    DEFAULT_WINDOWS_ASSET_NAME,
    GITHUB_REPOSITORY,
    VERSION_MANIFEST_URL,
)


@dataclass
class UpdateInfo:
    version: str
    notes: str
    download_url: str
    platform: str
    asset_name: str


def get_current_version() -> str:
    """Return the current app version."""
    return APP_VERSION


def _version_key(version: str) -> tuple:
    parts = []
    for item in version.strip().lstrip("v").split("."):
        if item.isdigit():
            parts.append(int(item))
        else:
            parts.append(item)
    return tuple(parts)


def is_update_available(current_version: str, latest_version: str) -> bool:
    """Return True when the latest version is newer than the current version."""
    return _version_key(latest_version) > _version_key(current_version)


def _get_platform_name() -> str:
    """Return the updater platform key."""
    if sys.platform == "darwin":
        return "macos"
    if sys.platform == "win32":
        return "windows"
    raise RuntimeError(f"Unsupported updater platform: {sys.platform}")


def _get_default_asset_name(platform_name: str) -> str:
    """Return the default release asset name for a platform."""
    if platform_name == "macos":
        return DEFAULT_MACOS_ASSET_NAME
    if platform_name == "windows":
        return DEFAULT_WINDOWS_ASSET_NAME
    raise RuntimeError(f"Unsupported updater platform: {platform_name}")


def _get_default_download_url(version: str, platform_name: str) -> str:
    """Build the default GitHub Releases asset URL."""
    return (
        f"https://github.com/{GITHUB_REPOSITORY}/releases/download/"
        f"v{version}/{_get_default_asset_name(platform_name)}"
    )


def fetch_latest_version_info(url: str = VERSION_MANIFEST_URL, timeout: int = 8) -> UpdateInfo:
    """Fetch version.json and return the latest update info for this platform."""
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Polaris-Updater"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))

    version = payload["version"]
    notes = payload.get("notes", "")
    platform_name = _get_platform_name()
    platform_payload = payload.get(platform_name, {})
    download_url = platform_payload.get("url")
    if not download_url:
        download_url = _get_default_download_url(version, platform_name)

    asset_name = platform_payload.get("asset_name") or Path(download_url).name
    return UpdateInfo(
        version=version,
        notes=notes,
        download_url=download_url,
        platform=platform_name,
        asset_name=asset_name,
    )


def write_updater_log(message: str) -> None:
    """Append a message to the updater log."""
    log_path = Path(get_updater_log_path())
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as log_file:
        log_file.write(message.rstrip() + "\n")


def clear_pending_update() -> None:
    """Remove any pending update marker."""
    pending_path = Path(get_update_pending_path())
    if pending_path.exists():
        pending_path.unlink()


def load_pending_update() -> dict | None:
    """Load pending update metadata if it exists."""
    pending_path = Path(get_update_pending_path())
    if not pending_path.exists():
        return None
    with open(pending_path, "r", encoding="utf-8") as pending_file:
        return json.load(pending_file)


def ensure_update_helper_script() -> str:
    """Return the bundled update helper module path."""
    return str(Path(get_resource_path("tools/updater/update_helper.py")))


def _find_staged_install_target(staging_dir: Path, platform_name: str) -> tuple[Path, Path]:
    """Return the staged install target and relaunch path."""
    if platform_name == "macos":
        staged_apps = sorted(staging_dir.rglob("*.app"))
        if not staged_apps:
            raise RuntimeError("Downloaded update archive did not contain a .app bundle.")
        staged_path = staged_apps[0]
        return staged_path, staged_path

    if platform_name == "windows":
        staged_exes = sorted(staging_dir.rglob("Polaris.exe"))
        if not staged_exes:
            raise RuntimeError("Downloaded update archive did not contain Polaris.exe.")
        relaunch_path = staged_exes[0]
        staged_path = relaunch_path.parent
        return staged_path, relaunch_path

    raise RuntimeError(f"Unsupported updater platform: {platform_name}")


def stage_update(update: UpdateInfo, install_target: str | None = None) -> dict:
    """Download and extract an app update, then write a pending marker."""
    install_target = install_target or get_current_install_target_path()
    if not install_target:
        raise RuntimeError("Could not determine the installed app path.")

    platform_name = update.platform or _get_platform_name()
    download_path = Path(get_update_download_path(update.asset_name or _get_default_asset_name(platform_name)))
    staging_dir = Path(get_update_staging_dir())
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)

    request = urllib.request.Request(
        update.download_url,
        headers={"User-Agent": "Polaris-Updater"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        download_path.write_bytes(response.read())

    with zipfile.ZipFile(download_path, "r") as archive:
        archive.extractall(staging_dir)

    staged_path, staged_launch_path = _find_staged_install_target(staging_dir, platform_name)
    current_launch_path = get_current_launch_path()
    if platform_name == "windows" and current_launch_path:
        install_launch_path = str(Path(install_target) / Path(current_launch_path).name)
    else:
        install_launch_path = install_target

    pending_data = {
        "current_version": get_current_version(),
        "target_version": update.version,
        "platform": platform_name,
        "asset_name": update.asset_name,
        "download_url": update.download_url,
        "notes": update.notes,
        "install_target": install_target,
        "install_launch_path": install_launch_path,
        "staged_path": str(staged_path),
        "staged_launch_path": str(staged_launch_path),
        "download_path": str(download_path),
        "staging_dir": str(staging_dir),
    }

    with open(get_update_pending_path(), "w", encoding="utf-8") as pending_file:
        json.dump(pending_data, pending_file, indent=2)

    return pending_data


def serialize_update_info(update: UpdateInfo | None) -> dict | None:
    """Convert update info to a JSON-serializable dict."""
    if update is None:
        return None
    return asdict(update)
