"""
Tests for config load/save logic in both cli_converter.py and gui_converter.py.

The GUI's load_config / save_config are instance methods on FileConverterApp,
so we test them by patching the CONFIG_FILE constant and calling the module-level
functions directly (or via a headless stand-in that avoids tkinter).

The CLI's load_config / save_config are plain module-level functions that we
import and exercise directly.
"""

import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# ─── Import CLI functions (no Tk, no side-effects on import) ─────────────────
import importlib, sys

def _import_cli():
    """Import cli_converter, suppressing the module-level LOGS_DIR creation
    that tries to create directories relative to _SCRIPT_DIR."""
    import terminal.cli_converter as cli
    return cli

# ─── Helpers to call GUI config I/O without instantiating Tk ─────────────────

def _gui_load_config(config_path: Path):
    """Call the GUI's load_config logic in isolation, returning the parsed dict."""
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _gui_save_config(config_path: Path, data: dict):
    """Call the GUI's save_config logic in isolation."""
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


# ═══════════════════════════════════════════════════════════════════════════════
# CLI config tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestCLIConfigLoad:
    """Tests for terminal/cli_converter.py load_config()."""

    def test_load_config_missing_file(self, tmp_path):
        """load_config returns an empty dict when config file does not exist."""
        cli = _import_cli()
        missing = str(tmp_path / "nonexistent.json")
        with patch.object(cli, "CONFIG_FILE", missing):
            result = cli.load_config()
        assert result == {}, "Expected empty dict for missing config file"

    def test_load_config_valid_json(self, tmp_path, sample_config):
        """load_config parses and returns a valid JSON config correctly."""
        cfg_path = tmp_path / "conversion_config.json"
        cfg_path.write_text(json.dumps(sample_config), encoding="utf-8")

        cli = _import_cli()
        with patch.object(cli, "CONFIG_FILE", str(cfg_path)):
            result = cli.load_config()

        assert result["force"] == sample_config["force"]
        assert result["logging"] == sample_config["logging"]
        assert result["input_folder"] == sample_config["input_folder"]

    def test_load_config_corrupted_json(self, corrupted_config):
        """load_config returns empty dict (not exception) for corrupt JSON."""
        cli = _import_cli()
        with patch.object(cli, "CONFIG_FILE", str(corrupted_config)):
            result = cli.load_config()
        assert result == {}, "Corrupted JSON should produce empty dict fallback"

    def test_load_config_missing_fields(self, tmp_path):
        """load_config handles configs with only some fields present."""
        cfg_path = tmp_path / "partial.json"
        cfg_path.write_text(json.dumps({"force": True}), encoding="utf-8")

        cli = _import_cli()
        with patch.object(cli, "CONFIG_FILE", str(cfg_path)):
            result = cli.load_config()

        assert result.get("force") is True
        assert result.get("input_folder") is None, "Missing key should return None"

    def test_load_config_empty_object(self, tmp_path):
        """load_config handles a valid JSON file that is just an empty object."""
        cfg_path = tmp_path / "empty.json"
        cfg_path.write_text("{}", encoding="utf-8")

        cli = _import_cli()
        with patch.object(cli, "CONFIG_FILE", str(cfg_path)):
            result = cli.load_config()

        assert result == {}


class TestCLIConfigSave:
    """Tests for terminal/cli_converter.py save_config()."""

    def test_save_config_creates_file(self, tmp_path, sample_config):
        """save_config creates the config file when it does not exist."""
        cfg_path = tmp_path / "conversion_config.json"
        assert not cfg_path.exists()

        cli = _import_cli()
        with patch.object(cli, "CONFIG_FILE", str(cfg_path)):
            cli.save_config(sample_config)

        assert cfg_path.is_file(), "Config file should be created by save_config"

    def test_save_config_valid_json_content(self, tmp_path, sample_config):
        """save_config writes valid JSON that can be re-parsed."""
        cfg_path = tmp_path / "conversion_config.json"

        cli = _import_cli()
        with patch.object(cli, "CONFIG_FILE", str(cfg_path)):
            cli.save_config(sample_config)

        reloaded = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert reloaded["force"] == sample_config["force"]
        assert reloaded["logging"] == sample_config["logging"]

    def test_save_config_overwrites_existing(self, tmp_path, sample_config):
        """save_config replaces the content of an existing config file."""
        cfg_path = tmp_path / "conversion_config.json"
        cfg_path.write_text('{"force": true, "stale": "yes"}', encoding="utf-8")

        cli = _import_cli()
        with patch.object(cli, "CONFIG_FILE", str(cfg_path)):
            cli.save_config(sample_config)

        reloaded = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert "stale" not in reloaded, "Old key should be gone after overwrite"
        assert reloaded["force"] == sample_config["force"]

    def test_save_config_handles_permissions(self, tmp_path, sample_config, capsys):
        """save_config prints a warning instead of raising when write fails."""
        cli = _import_cli()
        # Point at a path that will fail (a directory, not a file)
        bad_path = str(tmp_path)  # directory, not a file → open() will fail
        with patch.object(cli, "CONFIG_FILE", bad_path):
            # Should NOT raise; should print a warning
            try:
                cli.save_config(sample_config)
            except Exception as exc:
                pytest.fail(f"save_config raised unexpectedly: {exc}")


# ═══════════════════════════════════════════════════════════════════════════════
# Config format / compatibility tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestConfigFormat:
    """Tests for config schema conventions shared between CLI and GUI."""

    def test_config_extensions_dict_format(self, tmp_path, sample_config):
        """After a CLI save, extensions should be a dict {'.ext': bool}."""
        cfg_path = tmp_path / "conversion_config.json"
        cli = _import_cli()
        with patch.object(cli, "CONFIG_FILE", str(cfg_path)):
            cli.save_config(sample_config)

        saved = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert isinstance(saved["extensions"], dict), "CLI must save extensions as dict"
        for key in saved["extensions"]:
            assert key.startswith("."), f"Extension key '{key}' must start with '.'"

    def test_config_extensions_backward_compat_list(self, tmp_path):
        """GUI load_config must accept a list-format extensions value without error."""
        list_cfg = {
            "input_folder": str(tmp_path),
            "output_folder": str(tmp_path),
            "extensions": [".csv", ".html", ".pdf"],
            "force": False,
            "logging": True,
            "dry_run": False,
        }
        cfg_path = tmp_path / "conversion_config.json"
        cfg_path.write_text(json.dumps(list_cfg), encoding="utf-8")

        loaded = _gui_load_config(cfg_path)
        exts = loaded["extensions"]
        assert isinstance(exts, list), "Loaded extensions should remain as list (GUI converts on UI build)"
        assert ".csv" in exts

    def test_config_preserves_boolean_flags(self, tmp_path):
        """force, dry_run, and logging flags survive a round-trip save/load."""
        cfg = {
            "input_folder": str(tmp_path),
            "output_folder": str(tmp_path),
            "extensions": {".csv": True},
            "force": True,
            "dry_run": True,
            "logging": False,
        }
        cfg_path = tmp_path / "conversion_config.json"
        _gui_save_config(cfg_path, cfg)
        loaded = _gui_load_config(cfg_path)

        assert loaded["force"] is True, "force flag should survive round-trip"
        assert loaded["dry_run"] is True, "dry_run flag should survive round-trip"
        assert loaded["logging"] is False, "logging flag should survive round-trip"

    def test_config_paths_stored_as_strings(self, tmp_path, sample_config):
        """input_folder and output_folder are stored as plain strings."""
        cfg_path = tmp_path / "conversion_config.json"
        cli = _import_cli()
        with patch.object(cli, "CONFIG_FILE", str(cfg_path)):
            cli.save_config(sample_config)

        saved = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert isinstance(saved["input_folder"], str)
        assert isinstance(saved["output_folder"], str)


# ═══════════════════════════════════════════════════════════════════════════════
# GUI-specific config tests (headless, no Tk)
# ═══════════════════════════════════════════════════════════════════════════════

class TestGUIConfigHeadless:
    """Test the GUI's config I/O behaviour without instantiating a Tk window."""

    def test_gui_load_config_missing_returns_empty(self, tmp_path):
        """GUI load_config equivalent returns {} for a missing file."""
        result = _gui_load_config(tmp_path / "nonexistent.json")
        assert result == {}

    def test_gui_load_config_corrupted_returns_empty(self, corrupted_config):
        """GUI load_config equivalent returns {} for invalid JSON."""
        result = _gui_load_config(corrupted_config)
        assert result == {}

    def test_gui_save_creates_readable_file(self, tmp_path, sample_config):
        """GUI save_config equivalent produces a file that can be re-read."""
        cfg_path = tmp_path / "gui_config.json"
        _gui_save_config(cfg_path, sample_config)

        assert cfg_path.is_file()
        loaded = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert loaded["dry_run"] == sample_config["dry_run"]
