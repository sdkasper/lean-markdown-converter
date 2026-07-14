"""Path resolution and path-safety primitives.

Covers: frozen-vs-dev resource/config/log locations and the security
boundary check used for both source collection and output path building
(NFR-001: path traversal prevention).
"""

import os
import sys
from pathlib import Path

from core.constants import APPDATA_VENDOR_DIR


def is_frozen() -> bool:
    """True when running inside a PyInstaller bundle."""
    return getattr(sys, "frozen", False)


def resource_path(rel_path: str) -> Path:
    """Resolve a bundled resource path in both dev and frozen modes."""
    if is_frozen():
        return Path(sys._MEIPASS) / rel_path  # type: ignore[attr-defined]
    return project_root() / rel_path


def project_root() -> Path:
    """Repository root in dev mode (parent of the core/ package)."""
    return Path(__file__).resolve().parent.parent


def exe_dir() -> Path:
    """Directory containing the running executable (frozen) or the project root (dev).

    Installer components (ffmpeg/ffprobe/exiftool) live in <exe_dir>/tools/.
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return project_root()


def app_data_dir() -> Path:
    """Writable per-user data dir. %APPDATA%/LeanProductivity when frozen, project root in dev."""
    if is_frozen():
        base = Path(os.environ.get("APPDATA", Path.home())) / APPDATA_VENDOR_DIR
    else:
        base = project_root()
    base.mkdir(parents=True, exist_ok=True)
    return base


def config_file_path() -> Path:
    if is_frozen():
        return app_data_dir() / "config.json"
    return app_data_dir() / "conversion_config.json"


def logs_dir() -> Path:
    d = app_data_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def is_safe_path(base_dir: Path, target: Path) -> bool:
    """True if *target* resolves to a location inside *base_dir*.

    Resolves symlinks/junctions and '..' components before comparing
    (string prefix comparison is not sufficient on Windows).
    """
    try:
        base_resolved = Path(base_dir).resolve()
        target_resolved = Path(target).resolve()
        target_resolved.relative_to(base_resolved)
        return True
    except (ValueError, OSError):
        return False
