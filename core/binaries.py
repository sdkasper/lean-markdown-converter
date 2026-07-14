"""External binary discovery and audio/EXIF availability checks.

Covers ffmpeg, ffprobe, and exiftool discovery for both dev mode (running
from source) and frozen mode (PyInstaller single-file exe with an installer
that drops optional components under <exe_dir>/tools/).

Discovery order for every tool:
1. shutil.which(name) — system PATH
2. env var override (FFMPEG_PATH / FFPROBE_PATH / EXIFTOOL_PATH), if it
   points to an existing file
3. <exe_dir>/tools/<name>.exe (installer layout: audio tools flat in tools/,
   exiftool zip extracts to tools/exiftool/exiftool.exe)
4. dev fallback: <project_root>/resources/bin/<name>.exe

Never crashes the app: write_startup_diagnostic() swallows all exceptions.
"""

import os
import shutil
from datetime import datetime
from pathlib import Path

from core.constants import VERSION
from core.paths import exe_dir, is_frozen, logs_dir, project_root


def find_tool(name: str, env_var: str | None = None, extra_locations: list[Path] | None = None) -> Path | None:
    """Locate an external binary by name, following the discovery order above.

    *name* is the bare executable name without extension (e.g. "ffmpeg").
    *extra_locations* are additional candidate file paths checked between the
    env var and the dev fallback (used for exiftool's nested tools/exiftool/
    installer layout).
    """
    which_result = shutil.which(name)
    if which_result:
        return Path(which_result)

    if env_var:
        env_value = os.environ.get(env_var)
        if env_value and Path(env_value).is_file():
            return Path(env_value)

    candidate = exe_dir() / "tools" / f"{name}.exe"
    if candidate.is_file():
        return candidate

    if extra_locations:
        for loc in extra_locations:
            if loc.is_file():
                return loc

    dev_candidate = project_root() / "resources" / "bin" / f"{name}.exe"
    if dev_candidate.is_file():
        return dev_candidate

    return None


def find_ffmpeg() -> Path | None:
    return find_tool("ffmpeg", env_var="FFMPEG_PATH")


def find_ffprobe() -> Path | None:
    return find_tool("ffprobe", env_var="FFPROBE_PATH")


def find_exiftool() -> Path | None:
    """Locate exiftool. On success, also sets EXIFTOOL_PATH so MarkItDown's
    own internal detection (via env var) picks up the same binary.
    """
    nested = exe_dir() / "tools" / "exiftool" / "exiftool.exe"
    found = find_tool("exiftool", env_var="EXIFTOOL_PATH", extra_locations=[nested])
    if found:
        os.environ["EXIFTOOL_PATH"] = str(found)
    return found


def audio_available() -> bool:
    """True only when both ffmpeg AND ffprobe are found — M4A specifically
    needs ffprobe to detect the container format.
    """
    return find_ffmpeg() is not None and find_ffprobe() is not None


def exiftool_available() -> bool:
    return find_exiftool() is not None


def configure_pydub() -> bool:
    """Point pydub's AudioSegment at the discovered ffmpeg/ffprobe binaries.

    Both-or-neither rule: only sets converter/ffprobe when BOTH tools are
    found, so pydub never ends up with a half-configured (broken) state.
    Returns whether configuration succeeded. Imports pydub lazily so this
    module has no import-time cost when audio isn't used.
    """
    ffmpeg_path = find_ffmpeg()
    ffprobe_path = find_ffprobe()
    if not ffmpeg_path or not ffprobe_path:
        return False

    from pydub import AudioSegment

    AudioSegment.converter = str(ffmpeg_path)
    AudioSegment.ffprobe = str(ffprobe_path)
    return True


def write_startup_diagnostic() -> Path | None:
    """Write a startup diagnostic log capturing binary discovery results.

    Never raises — any failure (e.g. logs_dir() unwritable) results in a
    silent None return, since diagnostics must never crash the app.
    """
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        diag_path = logs_dir() / "startup_diagnostic.log"

        ffmpeg_path = find_ffmpeg()
        ffprobe_path = find_ffprobe()
        exiftool_path = find_exiftool()
        pydub_ok = configure_pydub()

        def describe(path: Path | None) -> str:
            if path is None:
                return "NOT FOUND"
            try:
                size = path.stat().st_size
                return f"{path} ({size} bytes)"
            except OSError:
                return f"{path} (size unknown)"

        lines = [
            f"[{ts}] {VERSION}",
            f"[{ts}] frozen: {is_frozen()}",
            f"[{ts}] ffmpeg: {describe(ffmpeg_path)}",
            f"[{ts}] ffprobe: {describe(ffprobe_path)}",
            f"[{ts}] exiftool: {describe(exiftool_path)}",
            f"[{ts}] pydub configured: {pydub_ok}",
        ]

        diag_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return diag_path
    except Exception:
        return None
