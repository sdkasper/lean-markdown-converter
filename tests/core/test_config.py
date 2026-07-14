"""Tests for core/config.py — ConverterConfig, load_config, save_config.

Covers dict/list extension round-tripping, corrupted/missing/non-dict JSON
fallback to defaults, partial-config merging, and extension normalization
(unknown extensions dropped, uppercase keys lowercased).

See tests/core/test_image_config.py for image_conversion-specific backward
compatibility tests, and tests/core/test_path_safety.py for core.paths
security tests.
"""

import json

import pytest

from core.config import ConverterConfig, load_config, save_config, normalize_extensions


# ═══════════════════════════════════════════════════════════════════════════
# normalize_extensions()
# ═══════════════════════════════════════════════════════════════════════════

class TestNormalizeExtensions:
    def test_dict_passthrough_coerces_bool(self):
        result = normalize_extensions({".pdf": True, ".csv": 1, ".docx": 0})
        assert result == {".pdf": True, ".csv": True, ".docx": False}

    def test_legacy_list_becomes_dict_all_true(self):
        result = normalize_extensions([".pdf", ".csv"])
        assert result == {".pdf": True, ".csv": True}

    def test_lowercases_keys(self):
        result = normalize_extensions({".PDF": True, ".CsV": True})
        assert result == {".pdf": True, ".csv": True}

    def test_drops_unsupported_extensions(self):
        result = normalize_extensions({".pdf": True, ".exe": True, ".bmp": True})
        assert result == {".pdf": True}

    def test_none_returns_empty_dict(self):
        assert normalize_extensions(None) == {}

    def test_garbage_type_returns_empty_dict(self):
        assert normalize_extensions(12345) == {}
        assert normalize_extensions("not a valid structure") == {}

    def test_empty_dict_and_list(self):
        assert normalize_extensions({}) == {}
        assert normalize_extensions([]) == {}


# ═══════════════════════════════════════════════════════════════════════════
# ConverterConfig.from_dict / to_dict
# ═══════════════════════════════════════════════════════════════════════════

class TestConverterConfigFromDict:
    def test_full_dict_round_trip(self, sample_config):
        cfg = ConverterConfig.from_dict(sample_config)
        assert cfg.input_folder == sample_config["input_folder"]
        assert cfg.output_folder == sample_config["output_folder"]
        assert cfg.extensions == sample_config["extensions"]
        assert cfg.force == sample_config["force"]
        assert cfg.dry_run == sample_config["dry_run"]
        assert cfg.logging == sample_config["logging"]

    def test_legacy_list_extensions_load_as_dict(self, tmp_path):
        raw = {
            "input_folder": str(tmp_path),
            "output_folder": str(tmp_path),
            "extensions": [".csv", ".html", ".pdf"],
            "force": False,
            "logging": True,
            "dry_run": False,
        }
        cfg = ConverterConfig.from_dict(raw)
        assert cfg.extensions == {".csv": True, ".html": True, ".pdf": True}

    def test_partial_config_merges_defaults(self):
        cfg = ConverterConfig.from_dict({"force": True})
        assert cfg.force is True
        assert cfg.input_folder == ""
        assert cfg.output_folder == ""
        assert cfg.extensions == {}
        assert cfg.logging is True  # dataclass default
        assert cfg.dry_run is False

    def test_empty_dict_gives_defaults(self):
        cfg = ConverterConfig.from_dict({})
        assert cfg == ConverterConfig()

    def test_to_dict_extensions_always_dict(self, sample_config):
        cfg = ConverterConfig.from_dict(sample_config)
        data = cfg.to_dict()
        assert isinstance(data["extensions"], dict)
        for key in data["extensions"]:
            assert key.startswith(".")

    def test_to_dict_is_json_serializable(self, sample_config):
        cfg = ConverterConfig.from_dict(sample_config)
        # Should not raise
        json.dumps(cfg.to_dict())


# ═══════════════════════════════════════════════════════════════════════════
# load_config()
# ═══════════════════════════════════════════════════════════════════════════

class TestLoadConfig:
    def test_missing_file_returns_defaults(self, tmp_path):
        cfg = load_config(tmp_path / "nonexistent.json")
        assert cfg == ConverterConfig()

    def test_corrupted_json_returns_defaults(self, corrupted_config):
        cfg = load_config(corrupted_config)
        assert cfg == ConverterConfig()

    def test_non_dict_json_returns_defaults(self, tmp_path):
        """A syntactically valid JSON array (not an object) must not raise."""
        cfg_path = tmp_path / "list.json"
        cfg_path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        cfg = load_config(cfg_path)
        assert cfg == ConverterConfig()

    def test_non_dict_json_scalar_returns_defaults(self, tmp_path):
        cfg_path = tmp_path / "scalar.json"
        cfg_path.write_text("42", encoding="utf-8")
        cfg = load_config(cfg_path)
        assert cfg == ConverterConfig()

    def test_valid_dict_loads_correctly(self, tmp_path, sample_config):
        cfg_path = tmp_path / "conversion_config.json"
        cfg_path.write_text(json.dumps(sample_config), encoding="utf-8")
        cfg = load_config(cfg_path)
        assert cfg.input_folder == sample_config["input_folder"]
        assert cfg.force == sample_config["force"]

    def test_partial_config_merges_defaults_from_disk(self, tmp_path):
        cfg_path = tmp_path / "partial.json"
        cfg_path.write_text(json.dumps({"force": True}), encoding="utf-8")
        cfg = load_config(cfg_path)
        assert cfg.force is True
        assert cfg.extensions == {}

    def test_uppercase_extension_keys_lowercased(self, tmp_path):
        cfg_path = tmp_path / "uppercase.json"
        cfg_path.write_text(json.dumps({"extensions": {".PDF": True, ".CSV": False}}), encoding="utf-8")
        cfg = load_config(cfg_path)
        assert cfg.extensions == {".pdf": True, ".csv": False}

    def test_unknown_extensions_dropped(self, tmp_path):
        cfg_path = tmp_path / "unknown_ext.json"
        cfg_path.write_text(
            json.dumps({"extensions": {".pdf": True, ".exe": True, ".zip": True}}),
            encoding="utf-8",
        )
        cfg = load_config(cfg_path)
        assert cfg.extensions == {".pdf": True}


# ═══════════════════════════════════════════════════════════════════════════
# save_config()
# ═══════════════════════════════════════════════════════════════════════════

class TestSaveConfig:
    def test_save_creates_parent_dir(self, tmp_path):
        cfg_path = tmp_path / "nested" / "dir" / "conversion_config.json"
        assert not cfg_path.parent.exists()
        save_config(ConverterConfig(force=True), cfg_path)
        assert cfg_path.is_file()

    def test_save_writes_valid_json(self, tmp_path, sample_config):
        cfg_path = tmp_path / "conversion_config.json"
        cfg = ConverterConfig.from_dict(sample_config)
        save_config(cfg, cfg_path)
        reloaded = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert reloaded["force"] == sample_config["force"]
        assert reloaded["logging"] == sample_config["logging"]

    def test_save_overwrites_existing_file(self, tmp_path):
        cfg_path = tmp_path / "conversion_config.json"
        cfg_path.write_text('{"force": true, "stale": "yes"}', encoding="utf-8")
        save_config(ConverterConfig(force=False), cfg_path)
        reloaded = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert "stale" not in reloaded
        assert reloaded["force"] is False

    def test_save_load_round_trip_preserves_all_fields(self, tmp_path, sample_config):
        cfg_path = tmp_path / "conversion_config.json"
        original = ConverterConfig.from_dict(sample_config)
        save_config(original, cfg_path)
        reloaded = load_config(cfg_path)
        assert reloaded == original

    def test_save_raises_oserror_on_bad_path(self, tmp_path):
        """Writing to a path that is itself a directory should raise OSError,
        letting the caller (GUI/CLI) decide how to surface the failure."""
        bad_path = tmp_path  # a directory, not a file
        with pytest.raises(OSError):
            save_config(ConverterConfig(), bad_path)
