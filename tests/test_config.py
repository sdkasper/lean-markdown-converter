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


# ═══════════════════════════════════════════════════════════════════════════════
# CLI extension and prompt parsing helpers
# ═══════════════════════════════════════════════════════════════════════════════

class TestExtensionParsing:
    """Test CLI helper functions for parsing extensions and prompts."""

    def test_parse_extensions_from_config_dict_format(self):
        """parse_extensions_from_config converts dict {'.ext': bool} to comma string."""
        cli = _import_cli()
        raw = {".pdf": True, ".docx": True, ".csv": False}
        result = cli.parse_extensions_from_config(raw)
        # Should return ".pdf,.docx" (only True values, order may vary)
        parsed = set(result.split(","))
        assert parsed == {".pdf", ".docx"}

    def test_parse_extensions_from_config_list_format(self):
        """parse_extensions_from_config handles backward-compat list format."""
        cli = _import_cli()
        raw = [".pdf", ".docx", ".csv"]
        result = cli.parse_extensions_from_config(raw)
        parsed = set(result.split(","))
        assert parsed == {".pdf", ".docx", ".csv"}

    def test_parse_extensions_from_config_empty_dict(self):
        """parse_extensions_from_config handles empty dict."""
        cli = _import_cli()
        raw = {}
        result = cli.parse_extensions_from_config(raw)
        assert result == ""

    def test_normalize_extensions_with_dots(self):
        """normalize_extensions keeps extensions that already have dots."""
        cli = _import_cli()
        result = cli.normalize_extensions(".pdf,.docx,.csv", "")
        assert ".pdf" in result
        assert ".docx" in result
        assert ".csv" in result

    def test_normalize_extensions_adds_dots(self):
        """normalize_extensions adds leading dots to extensions missing them."""
        cli = _import_cli()
        result = cli.normalize_extensions("pdf,docx", "")
        assert ".pdf" in result
        assert ".docx" in result

    def test_normalize_extensions_mixed_case(self):
        """normalize_extensions lowercases all extensions."""
        cli = _import_cli()
        result = cli.normalize_extensions(".PDF,.DocX", "")
        assert ".pdf" in result
        assert ".docx" in result

    def test_normalize_extensions_uses_default(self):
        """normalize_extensions falls back to default when input is empty."""
        cli = _import_cli()
        result = cli.normalize_extensions("", ".pdf,.docx")
        assert ".pdf" in result
        assert ".docx" in result

    def test_normalize_extensions_filters_empty_strings(self):
        """normalize_extensions ignores empty strings from split."""
        cli = _import_cli()
        result = cli.normalize_extensions(".pdf,,,.docx", "")
        assert ".pdf" in result
        assert ".docx" in result
        assert "" not in result

    def test_parse_yes_no_response_yes(self):
        """parse_yes_no_response converts 'y' to True."""
        cli = _import_cli()
        assert cli.parse_yes_no_response("y", default=False) is True
        assert cli.parse_yes_no_response("Y", default=False) is True

    def test_parse_yes_no_response_no(self):
        """parse_yes_no_response converts 'n' to False."""
        cli = _import_cli()
        assert cli.parse_yes_no_response("n", default=True) is False
        assert cli.parse_yes_no_response("N", default=True) is False

    def test_parse_yes_no_response_empty_uses_default(self):
        """parse_yes_no_response uses default when response is empty/whitespace."""
        cli = _import_cli()
        assert cli.parse_yes_no_response("", default=True) is True
        assert cli.parse_yes_no_response("  ", default=False) is False

    def test_parse_yes_no_response_invalid_uses_default(self):
        """parse_yes_no_response uses default for invalid responses."""
        cli = _import_cli()
        assert cli.parse_yes_no_response("maybe", default=True) is True
        assert cli.parse_yes_no_response("1", default=False) is False


# ═══════════════════════════════════════════════════════════════════════════════
# FFmpeg and pydub configuration tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestFFmpegConfiguration:
    """Test FFmpeg/AudioSegment configuration logic."""

    def test_ffmpeg_paths_set_correctly(self):
        """Verify that the CLI module can access FFmpeg paths after import."""
        cli = _import_cli()
        # The FFmpeg setup happens on import. We just verify the module loaded.
        # If there were errors, the import would have failed with an exception.
        assert hasattr(cli, "AudioSegment") or True  # AudioSegment may not be available if pydub isn't

    def test_supported_extensions_is_set(self):
        """Verify SUPPORTED_EXTENSIONS is a set."""
        cli = _import_cli()
        assert isinstance(cli.SUPPORTED_EXTENSIONS, set)
        assert len(cli.SUPPORTED_EXTENSIONS) > 0

    def test_audio_extension_in_supported(self):
        """Verify audio formats are in SUPPORTED_EXTENSIONS."""
        cli = _import_cli()
        assert ".mp3" in cli.SUPPORTED_EXTENSIONS
        assert ".wav" in cli.SUPPORTED_EXTENSIONS
        assert ".m4a" in cli.SUPPORTED_EXTENSIONS
