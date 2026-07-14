"""Tests for core/binaries.py — external binary discovery and audio/EXIF checks.

Every test mocks shutil.which, os.environ, and filesystem existence checks so
none of them depend on this machine's actual PATH state (this dev machine
has a real exiftool install — tests must pass regardless of that).
"""

import os
import sys
import types

import pytest

from core import binaries


@pytest.fixture(autouse=True)
def _preserve_exiftool_env():
    """find_exiftool() sets os.environ["EXIFTOOL_PATH"] as a deliberate side
    effect (MarkItDown reads it at construction). Tests here trigger it with
    fake temp paths, and monkeypatch cannot revert mutations the function
    itself makes - without this guard, a stale fake path leaks into later
    real-MarkItDown tests and breaks every audio/image conversion.
    """
    saved = os.environ.get("EXIFTOOL_PATH")
    yield
    if saved is None:
        os.environ.pop("EXIFTOOL_PATH", None)
    else:
        os.environ["EXIFTOOL_PATH"] = saved


# ─── find_tool ordering ────────────────────────────────────────────────────

def test_find_tool_which_hit_wins(monkeypatch):
    monkeypatch.setattr(binaries.shutil, "which", lambda name: r"C:\PATH\ffmpeg.exe")
    result = binaries.find_tool("ffmpeg", env_var="FFMPEG_PATH")
    assert result == binaries.Path(r"C:\PATH\ffmpeg.exe")


def test_find_tool_env_var_wins_when_which_misses(monkeypatch, tmp_path):
    env_file = tmp_path / "ffmpeg.exe"
    env_file.write_bytes(b"fake")
    monkeypatch.setattr(binaries.shutil, "which", lambda name: None)
    monkeypatch.setenv("FFMPEG_PATH", str(env_file))
    result = binaries.find_tool("ffmpeg", env_var="FFMPEG_PATH")
    assert result == env_file


def test_find_tool_env_var_ignored_if_missing_file(monkeypatch, tmp_path):
    monkeypatch.setattr(binaries.shutil, "which", lambda name: None)
    monkeypatch.setenv("FFMPEG_PATH", str(tmp_path / "does_not_exist.exe"))
    monkeypatch.setattr(binaries, "exe_dir", lambda: tmp_path / "nonexistent_exe_dir")
    monkeypatch.setattr(binaries, "project_root", lambda: tmp_path / "nonexistent_project_root")
    result = binaries.find_tool("ffmpeg", env_var="FFMPEG_PATH")
    assert result is None


def test_find_tool_tools_dir_found_when_which_and_env_miss(monkeypatch, tmp_path):
    exe_dir_path = tmp_path / "exe_dir"
    tools_dir = exe_dir_path / "tools"
    tools_dir.mkdir(parents=True)
    tool_file = tools_dir / "ffmpeg.exe"
    tool_file.write_bytes(b"fake")

    monkeypatch.setattr(binaries.shutil, "which", lambda name: None)
    monkeypatch.delenv("FFMPEG_PATH", raising=False)
    monkeypatch.setattr(binaries, "exe_dir", lambda: exe_dir_path)

    result = binaries.find_tool("ffmpeg", env_var="FFMPEG_PATH")
    assert result == tool_file


def test_find_tool_dev_resources_bin_last(monkeypatch, tmp_path):
    project_root_path = tmp_path / "project_root"
    dev_dir = project_root_path / "resources" / "bin"
    dev_dir.mkdir(parents=True)
    dev_file = dev_dir / "ffmpeg.exe"
    dev_file.write_bytes(b"fake")

    exe_dir_path = tmp_path / "exe_dir"  # tools/ subdir doesn't exist here

    monkeypatch.setattr(binaries.shutil, "which", lambda name: None)
    monkeypatch.delenv("FFMPEG_PATH", raising=False)
    monkeypatch.setattr(binaries, "exe_dir", lambda: exe_dir_path)
    monkeypatch.setattr(binaries, "project_root", lambda: project_root_path)

    result = binaries.find_tool("ffmpeg", env_var="FFMPEG_PATH")
    assert result == dev_file


def test_find_tool_nothing_found_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr(binaries.shutil, "which", lambda name: None)
    monkeypatch.delenv("FFMPEG_PATH", raising=False)
    monkeypatch.setattr(binaries, "exe_dir", lambda: tmp_path / "exe_dir_missing")
    monkeypatch.setattr(binaries, "project_root", lambda: tmp_path / "project_root_missing")

    result = binaries.find_tool("ffmpeg", env_var="FFMPEG_PATH")
    assert result is None


def test_find_tool_extra_locations_checked(monkeypatch, tmp_path):
    nested = tmp_path / "nested" / "exiftool.exe"
    nested.parent.mkdir(parents=True)
    nested.write_bytes(b"fake")

    monkeypatch.setattr(binaries.shutil, "which", lambda name: None)
    monkeypatch.delenv("EXIFTOOL_PATH", raising=False)
    monkeypatch.setattr(binaries, "exe_dir", lambda: tmp_path / "exe_dir_missing")
    monkeypatch.setattr(binaries, "project_root", lambda: tmp_path / "project_root_missing")

    result = binaries.find_tool("exiftool", env_var="EXIFTOOL_PATH", extra_locations=[nested])
    assert result == nested


# ─── find_ffmpeg / find_ffprobe / find_exiftool ────────────────────────────

def test_find_ffmpeg_delegates_to_find_tool(monkeypatch):
    captured = {}

    def fake_find_tool(name, env_var=None, extra_locations=None):
        captured["name"] = name
        captured["env_var"] = env_var
        return binaries.Path("resolved.exe")

    monkeypatch.setattr(binaries, "find_tool", fake_find_tool)
    result = binaries.find_ffmpeg()
    assert captured == {"name": "ffmpeg", "env_var": "FFMPEG_PATH"}
    assert result == binaries.Path("resolved.exe")


def test_find_ffprobe_delegates_to_find_tool(monkeypatch):
    captured = {}

    def fake_find_tool(name, env_var=None, extra_locations=None):
        captured["name"] = name
        captured["env_var"] = env_var
        return binaries.Path("resolved.exe")

    monkeypatch.setattr(binaries, "find_tool", fake_find_tool)
    result = binaries.find_ffprobe()
    assert captured == {"name": "ffprobe", "env_var": "FFPROBE_PATH"}
    assert result == binaries.Path("resolved.exe")


def test_find_exiftool_sets_env_var_on_success(monkeypatch, tmp_path):
    exiftool_file = tmp_path / "exiftool.exe"
    exiftool_file.write_bytes(b"fake")

    monkeypatch.delenv("EXIFTOOL_PATH", raising=False)
    monkeypatch.setattr(binaries.shutil, "which", lambda name: str(exiftool_file))

    result = binaries.find_exiftool()
    assert result == exiftool_file
    assert os.environ["EXIFTOOL_PATH"] == str(exiftool_file)


def test_find_exiftool_no_env_var_set_when_not_found(monkeypatch, tmp_path):
    monkeypatch.delenv("EXIFTOOL_PATH", raising=False)
    monkeypatch.setattr(binaries.shutil, "which", lambda name: None)
    monkeypatch.setattr(binaries, "exe_dir", lambda: tmp_path / "exe_dir_missing")
    monkeypatch.setattr(binaries, "project_root", lambda: tmp_path / "project_root_missing")

    result = binaries.find_exiftool()
    assert result is None
    assert "EXIFTOOL_PATH" not in os.environ


# ─── audio_available / exiftool_available ──────────────────────────────────

def test_audio_available_needs_both(monkeypatch):
    monkeypatch.setattr(binaries, "find_ffmpeg", lambda: binaries.Path("ffmpeg.exe"))
    monkeypatch.setattr(binaries, "find_ffprobe", lambda: None)
    assert binaries.audio_available() is False


def test_audio_available_true_when_both_found(monkeypatch):
    monkeypatch.setattr(binaries, "find_ffmpeg", lambda: binaries.Path("ffmpeg.exe"))
    monkeypatch.setattr(binaries, "find_ffprobe", lambda: binaries.Path("ffprobe.exe"))
    assert binaries.audio_available() is True


def test_exiftool_available_true(monkeypatch):
    monkeypatch.setattr(binaries, "find_exiftool", lambda: binaries.Path("exiftool.exe"))
    assert binaries.exiftool_available() is True


def test_exiftool_available_false(monkeypatch):
    monkeypatch.setattr(binaries, "find_exiftool", lambda: None)
    assert binaries.exiftool_available() is False


# ─── configure_pydub (both-or-neither) ─────────────────────────────────────

def _install_fake_pydub(monkeypatch):
    """Inject a fake pydub module into sys.modules so configure_pydub's lazy
    import picks it up without requiring the real dependency behavior.
    """
    fake_module = types.ModuleType("pydub")

    class FakeAudioSegment:
        converter = None
        ffprobe = None

    fake_module.AudioSegment = FakeAudioSegment
    monkeypatch.setitem(sys.modules, "pydub", fake_module)
    return FakeAudioSegment


def test_configure_pydub_both_found_configures(monkeypatch):
    fake_segment = _install_fake_pydub(monkeypatch)
    monkeypatch.setattr(binaries, "find_ffmpeg", lambda: binaries.Path("ffmpeg.exe"))
    monkeypatch.setattr(binaries, "find_ffprobe", lambda: binaries.Path("ffprobe.exe"))

    result = binaries.configure_pydub()

    assert result is True
    assert fake_segment.converter == "ffmpeg.exe"
    assert fake_segment.ffprobe == "ffprobe.exe"


def test_configure_pydub_only_ffmpeg_found_does_not_configure(monkeypatch):
    fake_segment = _install_fake_pydub(monkeypatch)
    monkeypatch.setattr(binaries, "find_ffmpeg", lambda: binaries.Path("ffmpeg.exe"))
    monkeypatch.setattr(binaries, "find_ffprobe", lambda: None)

    result = binaries.configure_pydub()

    assert result is False
    assert fake_segment.converter is None
    assert fake_segment.ffprobe is None


def test_configure_pydub_only_ffprobe_found_does_not_configure(monkeypatch):
    fake_segment = _install_fake_pydub(monkeypatch)
    monkeypatch.setattr(binaries, "find_ffmpeg", lambda: None)
    monkeypatch.setattr(binaries, "find_ffprobe", lambda: binaries.Path("ffprobe.exe"))

    result = binaries.configure_pydub()

    assert result is False
    assert fake_segment.converter is None
    assert fake_segment.ffprobe is None


def test_configure_pydub_neither_found(monkeypatch):
    fake_segment = _install_fake_pydub(monkeypatch)
    monkeypatch.setattr(binaries, "find_ffmpeg", lambda: None)
    monkeypatch.setattr(binaries, "find_ffprobe", lambda: None)

    result = binaries.configure_pydub()

    assert result is False
    assert fake_segment.converter is None
    assert fake_segment.ffprobe is None


# ─── write_startup_diagnostic ──────────────────────────────────────────────

def test_write_startup_diagnostic_creates_file_with_expected_content(monkeypatch, tmp_path):
    monkeypatch.setattr(binaries, "logs_dir", lambda: tmp_path)
    monkeypatch.setattr(binaries, "find_ffmpeg", lambda: binaries.Path("ffmpeg.exe"))
    monkeypatch.setattr(binaries, "find_ffprobe", lambda: binaries.Path("ffprobe.exe"))
    monkeypatch.setattr(binaries, "find_exiftool", lambda: None)
    monkeypatch.setattr(binaries, "configure_pydub", lambda: True)
    monkeypatch.setattr(binaries, "is_frozen", lambda: False)

    result = binaries.write_startup_diagnostic()

    assert result == tmp_path / "startup_diagnostic.log"
    content = result.read_text(encoding="utf-8")
    assert binaries.VERSION in content
    assert "frozen: False" in content
    assert "ffmpeg.exe" in content
    assert "ffprobe.exe" in content
    assert "exiftool: NOT FOUND" in content
    assert "pydub configured: True" in content


def test_write_startup_diagnostic_swallows_exceptions(monkeypatch):
    def raise_error():
        raise OSError("logs dir unavailable")

    monkeypatch.setattr(binaries, "logs_dir", raise_error)

    result = binaries.write_startup_diagnostic()

    assert result is None
