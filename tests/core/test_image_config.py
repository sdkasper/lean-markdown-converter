"""Tests for core/config.py image_conversion backward compatibility.

The whole point of this module: pre-v1.1.0 configs (no image_conversion key
at all) must keep loading as "feature off, EXIF-only fallback" with zero
migration code, and post-v1.1.0 configs (full block) must round-trip exactly.
"""

import json

import pytest

from core.config import ConverterConfig, load_config, save_config, DEFAULT_IMAGE_CONVERSION


FULL_IMAGE_BLOCK = {
    "enabled": True,
    "mode": "ocr",
    "provider": "custom",
    "api_key": "sk-test-12345",
    "model": "gpt-4o",
    "base_url": "https://api.example.com/v1",
}


class TestImageConversionAbsent:
    """Pre-pre-v1.1.0 configs: no image_conversion key at all."""

    def test_from_dict_missing_key_defaults_to_exif_off(self):
        cfg = ConverterConfig.from_dict({"input_folder": "C:/x"})
        assert cfg.image_conversion["enabled"] is False
        assert cfg.image_conversion["mode"] == "exif"
        assert cfg.image_conversion["provider"] == "gemini"

    def test_load_config_missing_key_matches_default_block(self, tmp_path):
        cfg_path = tmp_path / "old_config.json"
        cfg_path.write_text(json.dumps({"input_folder": "C:/x", "force": True}), encoding="utf-8")
        cfg = load_config(cfg_path)
        assert cfg.image_conversion == DEFAULT_IMAGE_CONVERSION

    def test_default_converter_config_has_image_conversion_off(self):
        cfg = ConverterConfig()
        assert cfg.image_conversion == DEFAULT_IMAGE_CONVERSION


class TestImageConversionPartial:
    """Partial image_conversion block: only some fields present."""

    def test_only_enabled_true_fills_rest_with_defaults(self):
        cfg = ConverterConfig.from_dict({"image_conversion": {"enabled": True}})
        assert cfg.image_conversion["enabled"] is True
        assert cfg.image_conversion["mode"] == "exif"
        assert cfg.image_conversion["provider"] == "gemini"
        assert cfg.image_conversion["model"] == "gemini-flash-latest"
        assert cfg.image_conversion["base_url"] == DEFAULT_IMAGE_CONVERSION["base_url"]

    def test_only_mode_present(self):
        cfg = ConverterConfig.from_dict({"image_conversion": {"mode": "ocr"}})
        assert cfg.image_conversion["mode"] == "ocr"
        assert cfg.image_conversion["enabled"] is False  # still default

    def test_non_dict_image_conversion_falls_back_to_defaults(self):
        cfg = ConverterConfig.from_dict({"image_conversion": "not a dict"})
        assert cfg.image_conversion == DEFAULT_IMAGE_CONVERSION


class TestImageConversionFullRoundTrip:
    def test_full_block_round_trips_exactly(self):
        cfg = ConverterConfig.from_dict({"image_conversion": FULL_IMAGE_BLOCK})
        assert cfg.image_conversion == FULL_IMAGE_BLOCK

    def test_full_block_save_load_round_trip(self, tmp_path):
        cfg_path = tmp_path / "conversion_config.json"
        original = ConverterConfig.from_dict({"image_conversion": FULL_IMAGE_BLOCK})
        save_config(original, cfg_path)
        reloaded = load_config(cfg_path)
        assert reloaded.image_conversion == FULL_IMAGE_BLOCK


class TestImageConversionInvalidValues:
    def test_invalid_mode_falls_back_to_exif(self):
        cfg = ConverterConfig.from_dict({"image_conversion": {"mode": "telepathy"}})
        assert cfg.image_conversion["mode"] == "exif"

    def test_invalid_provider_falls_back_to_gemini(self):
        cfg = ConverterConfig.from_dict({"image_conversion": {"provider": "skynet"}})
        assert cfg.image_conversion["provider"] == "gemini"

    def test_invalid_mode_and_provider_together(self):
        cfg = ConverterConfig.from_dict(
            {"image_conversion": {"mode": "bogus", "provider": "bogus", "enabled": True}}
        )
        assert cfg.image_conversion["mode"] == "exif"
        assert cfg.image_conversion["provider"] == "gemini"
        assert cfg.image_conversion["enabled"] is True  # unaffected by mode/provider fallback


class TestApiKeyHandling:
    """api_key must round-trip in the file, and this module must never log it."""

    def test_api_key_round_trips(self, tmp_path):
        cfg_path = tmp_path / "conversion_config.json"
        original = ConverterConfig.from_dict(
            {"image_conversion": {"api_key": "sk-supersecret-abc123"}}
        )
        save_config(original, cfg_path)
        reloaded = load_config(cfg_path)
        assert reloaded.image_conversion["api_key"] == "sk-supersecret-abc123"

    def test_api_key_present_in_saved_file_on_disk(self, tmp_path):
        """The key is stored in plaintext in the file (documented caveat) —
        confirm it lands in the file rather than being stripped or masked."""
        cfg_path = tmp_path / "conversion_config.json"
        original = ConverterConfig.from_dict(
            {"image_conversion": {"api_key": "sk-supersecret-abc123"}}
        )
        save_config(original, cfg_path)
        raw_text = cfg_path.read_text(encoding="utf-8")
        assert "sk-supersecret-abc123" in raw_text

    def test_config_module_never_logs(self, capsys):
        """core.config has no logging/print calls — assert no stray stdout
        output when constructing/saving a config containing an api key."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as d:
            cfg_path = Path(d) / "conversion_config.json"
            cfg = ConverterConfig.from_dict(
                {"image_conversion": {"api_key": "sk-should-not-be-printed"}}
            )
            save_config(cfg, cfg_path)
            load_config(cfg_path)

        captured = capsys.readouterr()
        assert "sk-should-not-be-printed" not in captured.out
        assert "sk-should-not-be-printed" not in captured.err
