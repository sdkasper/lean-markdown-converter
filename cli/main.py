"""Lean Markdown Converter - interactive terminal CLI.

Thin interactive layer over the core/ package (v2.0.0 rebuild). This module
owns prompt wording, input parsing, and I/O sequencing only - all conversion
logic (file discovery, path safety, MarkItDown/LLM wiring, the conversion
loop, and logging) lives in core.* and is exercised by tests/core/.

Run directly: python cli/main.py
"""

import subprocess
import sys
from pathlib import Path

from core.binaries import (
    audio_available,
    configure_pydub,
    exiftool_available,
    write_startup_diagnostic,
)
from core.config import ConverterConfig, load_config, save_config
from core.constants import (
    APP_NAME,
    AUDIO_EXTENSIONS,
    AUTHOR_NAME,
    IMAGE_EXTENSIONS,
    SUPPORTED_EXTENSIONS,
    VERSION,
)
from core.engine import ConversionCounts, run_conversion
from core.llm_factory import PROVIDER_PRESETS, LLMConfigError, build_markitdown, resolve_llm_prompt
from core.logging_util import RunLogger, format_summary
from core.paths import logs_dir
from core.scanner import collect_files


# ─── SMALL INPUT HELPERS ───────────────────────────────────────────────────

def prompt_yes_no(prompt_msg: str, default: bool) -> bool:
    """Ask a (y/n) question. Blank or unrecognized input falls back to *default*."""
    default_str = "y" if default else "n"
    raw = input(f"{prompt_msg} (y/n) [{default_str}]: ").strip().lower()
    if raw == "y":
        return True
    if raw == "n":
        return False
    return default


def prompt_input_folder(default: str) -> Path:
    """Prompt for the input folder. Must already exist - re-prompts otherwise."""
    while True:
        raw = input(f"Enter input folder path [{default}]: ").strip().strip('"')
        path_str = raw or default
        if not path_str:
            print("Error: Input folder path is required.")
            continue

        path = Path(path_str)
        if path.is_dir():
            return path

        print(f"Path does not exist: {path}")


def prompt_output_folder(default: str) -> Path:
    """Prompt for the output folder. Offers to create it if missing."""
    while True:
        raw = input(f"Enter output folder path [{default}]: ").strip().strip('"')
        path_str = raw or default
        if not path_str:
            print("Error: Output folder path is required.")
            continue

        path = Path(path_str)
        if path.is_dir():
            return path

        if prompt_yes_no(f"Path does not exist: {path}. Create it?", False):
            try:
                path.mkdir(parents=True, exist_ok=True)
                return path
            except OSError as e:
                print(f"Failed to create directory: {e}")
        # else: loop back and re-prompt


def prompt_extensions(default_extensions: dict) -> dict | None:
    """Prompt for a comma-separated extension list (or 'all').

    Returns a {'.ext': True} dict of the supported subset, or None if the
    resulting selection is empty (caller is responsible for exiting).
    """
    default_ext_str = ",".join(sorted(ext for ext, on in default_extensions.items() if on))
    raw = input(
        f"Enter file extensions (comma-separated, or 'all') [{default_ext_str}]: "
    ).strip()
    raw = raw or default_ext_str

    if raw.strip().lower() == "all":
        return {ext: True for ext in sorted(SUPPORTED_EXTENSIONS)}

    requested = {
        (e if e.startswith(".") else f".{e}")
        for ext in raw.split(",")
        if (e := ext.strip().lower())
    }

    unsupported = requested - SUPPORTED_EXTENSIONS
    if unsupported:
        print(f"Warning: Ignoring unsupported extension(s): {', '.join(sorted(unsupported))}")

    supported = requested & SUPPORTED_EXTENSIONS
    if not supported:
        return None

    return {ext: True for ext in sorted(supported)}


def prompt_image_conversion(current: dict) -> dict:
    """Prompt for the image_conversion block when jpg/jpeg/png are selected.

    *current* is the previously loaded/saved image_conversion dict (already
    normalized by core.config). Returns an updated copy - never mutates the
    input dict in place.
    """
    cfg = dict(current)

    enabled = prompt_yes_no("Enable image conversion (EXIF/OCR)?", cfg.get("enabled", False))
    cfg["enabled"] = enabled
    if not enabled:
        return cfg

    mode_default = "2" if cfg.get("mode") == "ocr" else "1"
    resp = input(
        f"Image mode: (1) EXIF metadata only  (2) Full OCR [{mode_default}]: "
    ).strip()
    mode = "ocr" if (resp or mode_default) == "2" else "exif"
    cfg["mode"] = mode

    if mode == "exif":
        if not exiftool_available():
            print(
                "Warning: exiftool not found on PATH or as a bundled component - "
                "image files will convert to empty output and be skipped."
            )
        return cfg

    # OCR mode - provider selection
    provider_map = {"1": "gemini", "2": "ollama", "3": "custom"}
    reverse_provider_map = {"gemini": "1", "ollama": "2", "custom": "3"}
    provider_default = reverse_provider_map.get(cfg.get("provider", "gemini"), "1")
    resp = input(
        f"LLM provider: (1) Gemini free tier  (2) Ollama local  (3) Custom [{provider_default}]: "
    ).strip()
    provider = provider_map.get(resp or provider_default, "gemini")
    cfg["provider"] = provider

    preset = PROVIDER_PRESETS.get(provider, {"base_url": "", "model": "", "needs_key": True})
    base_url_default = cfg.get("base_url") or preset["base_url"]
    model_default = cfg.get("model") or preset["model"]

    base_url = input(f"Base URL [{base_url_default}]: ").strip() or base_url_default
    model = input(f"Model name [{model_default}]: ").strip() or model_default
    cfg["base_url"] = base_url
    cfg["model"] = model

    if preset.get("needs_key", True):
        # Never echo the key back in any subsequent print/log line.
        api_key = input("API key (leave blank to keep existing): ").strip()
        if api_key:
            cfg["api_key"] = api_key
    # ollama needs no key; leave whatever was previously stored untouched.

    return cfg


# ─── MAIN ───────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print(f"{APP_NAME} {VERSION}")
    print(AUTHOR_NAME)
    print("=" * 60)

    write_startup_diagnostic()
    configure_pydub()

    config = load_config()

    input_folder = prompt_input_folder(config.input_folder)
    output_folder = prompt_output_folder(config.output_folder)

    extensions = prompt_extensions(config.extensions)
    if extensions is None:
        print("Error: No supported extensions selected. Exiting.")
        sys.exit(1)

    ext_set = set(extensions.keys())

    if ext_set & AUDIO_EXTENSIONS and not audio_available():
        print(
            "Warning: MP3/M4A/WAV conversion needs ffmpeg and ffprobe, which were not found. "
            "Audio files will fail to convert."
        )

    image_conversion = dict(config.image_conversion)
    if ext_set & IMAGE_EXTENSIONS:
        image_conversion = prompt_image_conversion(image_conversion)

    force = prompt_yes_no("Force convert all files?", config.force)
    logging_enabled = prompt_yes_no("Enable logging?", config.logging)
    dry_run = prompt_yes_no("Dry run only?", config.dry_run)

    new_config = ConverterConfig(
        input_folder=str(input_folder),
        output_folder=str(output_folder),
        extensions=extensions,
        force=force,
        logging=logging_enabled,
        dry_run=dry_run,
        image_conversion=image_conversion,
    )
    save_config(new_config)

    scan = collect_files(input_folder, output_folder, ext_set, force=force)

    print(
        f"\nFound {len(scan.tasks)} file(s) to convert, "
        f"{scan.skipped_up_to_date} skipped (up-to-date), "
        f"{scan.skipped_unsafe} skipped (unsafe path)."
    )

    if not scan.tasks:
        print("Nothing to convert.")
        sys.exit(0)

    if dry_run:
        print("\n=== DRY RUN SUMMARY ===")
        for task in scan.tasks:
            print(f"Would convert: {task.src} -> {task.dst}")
        print(f"Files that would be converted: {len(scan.tasks)}")

        if not prompt_yes_no("Proceed with actual conversion?", False):
            sys.exit(0)
        dry_run = False

    try:
        md = build_markitdown(image_conversion)
    except LLMConfigError as e:
        print(f"Error: {e}")
        sys.exit(1)

    run_logger = RunLogger(logs_dir(), VERSION, enabled=logging_enabled)

    def on_progress(i: int, total: int, name: str) -> None:
        print(f"[{i}/{total}] {name}")

    try:
        counts = run_conversion(
            scan.tasks, md, on_progress=on_progress, should_cancel=None,
            run_logger=run_logger, llm_prompt=resolve_llm_prompt(image_conversion),
        )
    except KeyboardInterrupt:
        counts = ConversionCounts(cancelled=True)
        print("\nCancelled by user (Ctrl+C).")

    print("\n" + format_summary(counts))

    if logging_enabled:
        log_path = run_logger.finalize(format_summary(counts))
        if log_path:
            print(f"\nLog saved to: {log_path}")
            if prompt_yes_no("Open log file?", False):
                subprocess.Popen(["notepad.exe", str(log_path)])

    if counts.cancelled:
        sys.exit(130)


if __name__ == "__main__":
    main()
