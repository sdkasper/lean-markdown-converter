"""Config load/save for Lean Markdown Converter.

Single source of truth for the ``ConverterConfig`` dataclass and the
``load_config`` / ``save_config`` functions consumed by both the GUI and
CLI layers. Replaces the ad-hoc dict-based config handling that used to be
duplicated in ``gui/gui_converter.py`` and ``terminal/cli_converter.py``.

Backward compatibility is the point of this module: configs written by the
pre-2.0.0 GUI/CLI (extensions as a list, no ``image_conversion`` key at all)
must continue to load without raising and without behavior change.
"""

import copy
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from core.constants import SUPPORTED_EXTENSIONS
from core.paths import config_file_path

# ─── IMAGE CONVERSION DEFAULTS ─────────────────────────────────────────────
# Master toggle + mode/provider selection for the image conversion feature
# (see project CLAUDE.md "Image Support" section). Absence of this whole
# key in a loaded config means "feature off, EXIF-only fallback" — no
# migration code is needed for pre-v1.1.0 configs.
DEFAULT_IMAGE_CONVERSION = {
    "enabled": False,
    "mode": "exif",             # "exif" | "ocr"
    "provider": "gemini",       # "gemini" | "ollama" | "custom"
    "api_key": "",
    "model": "gemini-flash-latest",
    "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
    # Optional OCR prompt override (config-file-only, no GUI widget).
    # Empty string = use core.llm_factory.DEFAULT_LLM_PROMPT (verbatim
    # transcription). Legacy configs without this key load unchanged.
    "llm_prompt": "",
}

_VALID_MODES = frozenset({"exif", "ocr"})
_VALID_PROVIDERS = frozenset({"gemini", "ollama", "custom"})


# ─── CONFIG DATACLASS ───────────────────────────────────────────────────────

@dataclass
class ConverterConfig:
    """In-memory representation of ``conversion_config.json``."""

    input_folder: str = ""
    output_folder: str = ""
    extensions: dict = field(default_factory=dict)
    force: bool = False
    logging: bool = True
    dry_run: bool = False
    image_conversion: dict = field(default_factory=lambda: copy.deepcopy(DEFAULT_IMAGE_CONVERSION))

    @classmethod
    def from_dict(cls, raw: dict) -> "ConverterConfig":
        """Build a ConverterConfig from a raw (possibly partial) dict.

        Never raises — unknown/missing fields fall back to dataclass
        defaults, and nested image_conversion fields are merged individually.
        """
        if not isinstance(raw, dict):
            raw = {}

        return cls(
            input_folder=raw.get("input_folder") or "",
            output_folder=raw.get("output_folder") or "",
            extensions=normalize_extensions(raw.get("extensions")),
            force=bool(raw.get("force", False)),
            logging=bool(raw.get("logging", True)),
            dry_run=bool(raw.get("dry_run", False)),
            image_conversion=_normalize_image_conversion(raw.get("image_conversion")),
        )

    def to_dict(self) -> dict:
        """JSON-serializable dict, extensions always as {'.ext': bool}."""
        return asdict(self)


# ─── EXTENSION NORMALIZATION ────────────────────────────────────────────────

def normalize_extensions(raw) -> dict:
    """Normalize raw extension config into a lowercase {'.ext': bool} dict.

    Accepts:
      - dict {'.ext': bool, ...}   (current GUI format) — values coerced to bool
      - list ['.ext', ...]         (legacy CLI format) — all treated as True
      - None / garbage             -> {}

    Entries not present in SUPPORTED_EXTENSIONS are dropped. Keys are
    lowercased so uppercase extensions from a hand-edited config still work.
    """
    result = {}

    if isinstance(raw, dict):
        items = raw.items()
    elif isinstance(raw, (list, tuple, set, frozenset)):
        items = ((ext, True) for ext in raw)
    else:
        return {}

    for key, value in items:
        if not isinstance(key, str):
            continue
        ext = key.strip().lower()
        if ext in SUPPORTED_EXTENSIONS:
            result[ext] = bool(value)

    return result


def _normalize_image_conversion(raw) -> dict:
    """Merge a raw (possibly partial/absent) image_conversion block with defaults.

    Missing key entirely, non-dict, or partial block -> missing fields filled
    from DEFAULT_IMAGE_CONVERSION. Unknown mode/provider values fall back to
    the default mode/provider rather than being rejected outright.
    """
    merged = copy.deepcopy(DEFAULT_IMAGE_CONVERSION)

    if not isinstance(raw, dict):
        return merged

    merged["enabled"] = bool(raw.get("enabled", merged["enabled"]))

    mode = raw.get("mode", merged["mode"])
    merged["mode"] = mode if mode in _VALID_MODES else merged["mode"]

    provider = raw.get("provider", merged["provider"])
    merged["provider"] = provider if provider in _VALID_PROVIDERS else merged["provider"]

    merged["api_key"] = raw.get("api_key", merged["api_key"])
    merged["model"] = raw.get("model", merged["model"])
    merged["base_url"] = raw.get("base_url", merged["base_url"])
    merged["llm_prompt"] = raw.get("llm_prompt", merged["llm_prompt"])

    return merged


# ─── LOAD / SAVE ─────────────────────────────────────────────────────────────

def load_config(path: Optional[Path] = None) -> ConverterConfig:
    """Load ConverterConfig from *path* (default: core.paths.config_file_path()).

    Never raises: a missing file, corrupted JSON, or valid-but-non-dict JSON
    (e.g. a top-level list) all fall back to ConverterConfig() defaults.
    """
    cfg_path = Path(path) if path is not None else config_file_path()

    try:
        raw_text = cfg_path.read_text(encoding="utf-8")
    except OSError:
        return ConverterConfig()

    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError:
        return ConverterConfig()

    if not isinstance(raw, dict):
        return ConverterConfig()

    return ConverterConfig.from_dict(raw)


def save_config(config: ConverterConfig, path: Optional[Path] = None) -> None:
    """Write *config* to *path* (default: core.paths.config_file_path()) as JSON.

    Ensures the parent directory exists. May raise OSError on write failure —
    callers are responsible for handling/reporting that (matches the existing
    GUI/CLI behavior of surfacing a warning rather than crashing).
    """
    cfg_path = Path(path) if path is not None else config_file_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)

    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, indent=4)
