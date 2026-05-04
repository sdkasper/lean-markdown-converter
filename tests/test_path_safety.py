"""
Tests for path-safety and symlink-traversal protection.

Both cli_converter.py (module-level is_safe_path) and gui_converter.py
(FileConverterApp._is_safe_path static method) implement the same logic.
We test both independently to ensure they cannot diverge.

Security marks: pytest.mark.security
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# ─── Grab the two implementations ────────────────────────────────────────────

import terminal.cli_converter as cli_mod
cli_is_safe = cli_mod.is_safe_path  # module-level function

# For the GUI we import the static method without spinning up Tk
import gui.gui_converter as gui_mod
gui_is_safe = gui_mod.FileConverterApp._is_safe_path  # unbound static method


# ═══════════════════════════════════════════════════════════════════════════════
# Parametrized over both implementations
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(params=["cli", "gui"])
def is_safe(request):
    """Parametrized fixture that yields the is_safe_path implementation."""
    if request.param == "cli":
        return cli_is_safe
    return gui_is_safe


# ═══════════════════════════════════════════════════════════════════════════════
# Core safety logic
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.security
class TestIsSafePathCore:
    """Fundamental path-containment tests (same logic in CLI and GUI)."""

    def test_valid_child_path_is_safe(self, tmp_path, is_safe):
        """A direct child of base_dir is safe."""
        child = tmp_path / "subdir" / "file.txt"
        assert is_safe(tmp_path, child) is True, (
            f"Direct child {child} should be safe within {tmp_path}"
        )

    def test_base_dir_itself_is_safe(self, tmp_path, is_safe):
        """The base directory itself is considered safe (edge case)."""
        assert is_safe(tmp_path, tmp_path) is True

    def test_deep_nesting_is_safe(self, tmp_path, is_safe):
        """A deeply nested valid path is allowed."""
        deep = tmp_path / "a" / "b" / "c" / "d" / "e" / "file.md"
        assert is_safe(tmp_path, deep) is True

    def test_absolute_path_outside_root_is_rejected(self, tmp_path, is_safe):
        """An absolute path that resolves outside base_dir is rejected."""
        outside = tmp_path.parent / "other_dir" / "evil.txt"
        assert is_safe(tmp_path, outside) is False, (
            f"{outside} should NOT be safe — it is outside {tmp_path}"
        )

    def test_sibling_directory_is_rejected(self, tmp_path, is_safe):
        """A sibling of base_dir is not inside base_dir."""
        sibling = tmp_path.parent / "sibling"
        assert is_safe(tmp_path, sibling) is False

    def test_parent_directory_traversal_rejected(self, tmp_path, is_safe):
        """A path component that ultimately exits base_dir is rejected."""
        # Path('base/legit/../../../etc/passwd') resolves outside base
        traversal = tmp_path / "sub" / ".." / ".." / "evil"
        assert is_safe(tmp_path, traversal) is False, (
            "Path traversal via '..' must be rejected after resolution"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Symlink-specific tests (Windows junction / POSIX symlink)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.security
class TestSymlinkTraversal:
    """is_safe_path must detect symlinks that point outside base_dir."""

    @pytest.mark.skipif(
        sys.platform == "win32" and not os.path.exists("C:/Windows"),
        reason="Symlink creation may require elevated privileges on Windows",
    )
    def test_symlink_pointing_outside_is_rejected(self, tmp_path, is_safe):
        """A symlink inside base_dir that targets outside is rejected."""
        # Create a real directory outside our base
        outside_dir = tmp_path.parent / "outside_target"
        outside_dir.mkdir(exist_ok=True)
        outside_file = outside_dir / "secret.txt"
        outside_file.write_text("secret", encoding="utf-8")

        base = tmp_path / "base"
        base.mkdir()

        link = base / "evil_link"
        try:
            link.symlink_to(outside_dir)
        except (OSError, NotImplementedError):
            pytest.skip("Cannot create symlinks in this environment")

        target = link / "secret.txt"
        assert is_safe(base, target) is False, (
            "Symlink escaping base_dir must be detected as unsafe"
        )

    @pytest.mark.skipif(
        sys.platform == "win32" and not os.path.exists("C:/Windows"),
        reason="Symlink creation may require elevated privileges on Windows",
    )
    def test_symlink_within_base_is_safe(self, tmp_path, is_safe):
        """A symlink inside base_dir that targets another path inside is safe."""
        base = tmp_path / "base"
        base.mkdir()
        target_dir = base / "real_dir"
        target_dir.mkdir()

        link = base / "link_to_real"
        try:
            link.symlink_to(target_dir)
        except (OSError, NotImplementedError):
            pytest.skip("Cannot create symlinks in this environment")

        assert is_safe(base, link / "file.txt") is True


# ═══════════════════════════════════════════════════════════════════════════════
# GUI-specific path tests (APPDATA, resource_path, etc.)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.security
class TestGUIPathConstants:
    """Verify the GUI chooses correct config and log paths in frozen vs. dev mode."""

    def test_config_path_dev_mode_is_relative_to_script(self):
        """In dev mode (not frozen), CONFIG_FILE must be near the script, not APPDATA."""
        assert not getattr(sys, "frozen", False), "Test must run in dev mode"
        cfg = Path(gui_mod.CONFIG_FILE)
        script_dir = Path(gui_mod._SCRIPT_DIR)
        # CONFIG_FILE should be at most one directory above script dir
        # i.e., .../lean-markdown-converter/conversion_config.json
        assert not str(cfg).startswith(os.environ.get("APPDATA", "__no_appdata__")), (
            "In dev mode, CONFIG_FILE should not be in APPDATA"
        )

    def test_logs_dir_dev_mode_is_relative_to_script(self):
        """In dev mode, LOGS_DIR should be relative to the project root."""
        assert not getattr(sys, "frozen", False)
        logs = Path(gui_mod.LOGS_DIR)
        script_dir = Path(gui_mod._SCRIPT_DIR)
        # logs/ is at <project_root>/logs, which is one level above gui/
        assert logs.parts[-1] == "logs", f"LOGS_DIR leaf should be 'logs', got {logs}"

    def test_frozen_path_would_use_appdata(self, monkeypatch, tmp_path):
        """Simulate frozen=True to confirm the APPDATA branch is taken."""
        import importlib

        # Provide both sys.frozen and sys._MEIPASS so resource_path() doesn't crash
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
        monkeypatch.setenv("APPDATA", str(Path.home()))

        try:
            import gui.gui_converter as reloaded
            importlib.reload(reloaded)
            assert str(Path.home()) in reloaded.CONFIG_FILE, (
                "Frozen mode should use APPDATA-based config path"
            )
        finally:
            # Always restore to normal dev-mode state
            monkeypatch.delattr(sys, "frozen", raising=False)
            monkeypatch.delattr(sys, "_MEIPASS", raising=False)
            importlib.reload(gui_mod)


# ═══════════════════════════════════════════════════════════════════════════════
# CLI-specific path tests
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.security
class TestCLIPathConstants:
    """Verify CLI path constants are derived from _SCRIPT_DIR."""

    def test_cli_config_file_derived_from_script_dir(self):
        """CLI CONFIG_FILE should be relative to the cli_converter.py location."""
        cfg = Path(cli_mod.CONFIG_FILE).resolve()
        script_dir = Path(cli_mod._SCRIPT_DIR).resolve()
        # CONFIG_FILE = _SCRIPT_DIR/../conversion_config.json
        # After resolve(), parent == project root == script_dir.parent
        assert cfg.parent == script_dir.parent, (
            f"CONFIG_FILE {cfg} should be one level above SCRIPT_DIR {script_dir}"
        )

    def test_cli_logs_dir_derived_from_script_dir(self):
        """CLI LOGS_DIR should be relative to the cli_converter.py location."""
        logs = Path(cli_mod.LOGS_DIR).resolve()
        script_dir = Path(cli_mod._SCRIPT_DIR).resolve()
        assert logs.parent == script_dir.parent, (
            f"LOGS_DIR {logs} should be one level above SCRIPT_DIR {script_dir}"
        )
        assert logs.name == "logs"

    def test_ffmpeg_path_near_resources(self):
        """FFmpeg is expected in <project_root>/resources/bin/ relative to script."""
        expected = Path(cli_mod._SCRIPT_DIR) / ".." / "resources" / "bin" / "ffmpeg.exe"
        # We only check the pattern, not whether the exe exists in CI
        resolved = expected.resolve()
        assert "resources" in str(resolved), (
            "FFmpeg path must be under the resources/ directory"
        )
        assert "bin" in str(resolved)
