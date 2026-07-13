# ─── APPLICATION METADATA ──────────────────────────────────────────────────
APP_NAME = "Lean Markdown Converter CLI"
APP_DESCRIPTION = "A no GUI batch converter for MarkItDown to convert various file formats to Markdown."
VERSION = "1.1.0"
AUTHOR_NAME = "Sascha D. Kasper - LeanProductivity"
HELP_URL = "https://github.com/microsoft/markitdown"
# ──────────────────────────────────────────────────────────────────────────

import os
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime
from markitdown import MarkItDown

# ─── CONFIGURATION AND PATHS ──────────────────────────────────────────────
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(_SCRIPT_DIR, "..", "conversion_config.json")
LOGS_DIR = os.path.join(_SCRIPT_DIR, "..", "logs")
os.makedirs(LOGS_DIR, exist_ok=True)
SUPPORTED_EXTENSIONS = {
    ".csv", ".doc", ".docx", ".epub", ".htm", ".html",
    ".ipynb", ".jpeg", ".jpg", ".json", ".m4a", ".mp3", ".msg", ".pdf", ".png",
    ".ppt", ".pptx", ".wav", ".xls", ".xlsx", ".xml"
}
# Note: .bmp, .gif, .tiff are NOT included — MarkItDown's ImageConverter only
# accepts .jpg/.jpeg/.png (verified against markitdown 0.1.5 and 0.1.6). Other
# image extensions raise UnsupportedFormatException regardless of LLM config.

# Optional: FFmpeg for audio support via pydub
# Only set custom ffmpeg paths if NOT in system PATH
# M4A audio transcription fails with custom absolute paths when system ffmpeg is available
try:
    from pydub import AudioSegment
    # Check if ffmpeg AND ffprobe are in PATH
    ffmpeg_in_path = subprocess.run(["where", "ffmpeg"], capture_output=True, text=True).returncode == 0
    ffprobe_in_path = subprocess.run(["where", "ffprobe"], capture_output=True, text=True).returncode == 0

    # Only set custom paths if BOTH binaries are NOT in PATH (e.g., bundled exe without system ffmpeg)
    if not ffmpeg_in_path or not ffprobe_in_path:
        ffmpeg_path = os.path.join(_SCRIPT_DIR, "..", "resources", "bin", "ffmpeg.exe")
        ffprobe_path = os.path.join(_SCRIPT_DIR, "..", "resources", "bin", "ffprobe.exe")
        if not Path(ffmpeg_path).is_file() or not Path(ffprobe_path).is_file():
            raise FileNotFoundError(f"FFmpeg/ffprobe not found at {ffmpeg_path} / {ffprobe_path}")
        AudioSegment.converter = ffmpeg_path
        AudioSegment.ffprobe = ffprobe_path
except ImportError:
    pass  # pydub not installed
except Exception as e:
    print(f"FFmpeg configuration warning: {e}")

# ─── LOAD OR PROMPT CONFIG ────────────────────────────────────────────────
def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Could not read settings file, using defaults. ({e})")
    return {}

def save_config(config):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f"Warning: Could not save settings. ({e})")

def is_safe_path(base_dir: Path, target: Path) -> bool:
    """Return True if target resolves to a path within base_dir (prevents symlink/junction traversal)."""
    try:
        target.resolve().relative_to(base_dir.resolve())
        return True
    except ValueError:
        return False

def prompt_path(prompt_msg: str, default: str = None) -> str:
    while True:
        raw = input(f"{prompt_msg} [{default or ''}]: ").strip().strip('"')
        path = raw or default
        if not path:
            continue
        path_obj = Path(path)
        if path_obj.exists():
            return str(path_obj)
        else:
            create = input(f"Path does not exist. Create it? (y/n): ").strip().lower()
            if create == 'y':
                try:
                    path_obj.mkdir(parents=True, exist_ok=True)
                    return str(path_obj)
                except Exception as e:
                    print(f"Failed to create directory: {e}")

def parse_extensions_from_config(raw_exts):
    """Parse extensions from config (handles both dict and list formats for backward compat)."""
    if isinstance(raw_exts, dict):
        return ','.join(k for k, v in raw_exts.items() if v)
    else:
        return ','.join(raw_exts)

def normalize_extensions(ext_input: str, default_ext_str: str) -> set:
    """Normalize comma-separated extension input into a set of lowercase extensions."""
    ext_raw = ext_input or default_ext_str
    requested_extensions = {
        (e if e.startswith(".") else f".{e}")
        for ext in ext_raw.split(",")
        if (e := ext.strip().lower())
    }
    return requested_extensions

def parse_yes_no_response(response: str, default: bool) -> bool:
    """Parse a yes/no response, with fallback to default for empty or invalid input."""
    r = response.strip().lower()
    if r == 'y':
        return True
    elif r == 'n':
        return False
    else:
        return default

if __name__ == "__main__":
    cfg = load_config()
    input_folder = Path(prompt_path("Enter input folder path", cfg.get("input_folder")))
    output_folder = Path(prompt_path("Enter output folder path", cfg.get("output_folder")))

    img_cfg = cfg.get("image_conversion", {})
    image_conversion_enabled = False
    image_mode = img_cfg.get("mode", "exif")
    image_provider = img_cfg.get("provider", "gemini")
    image_api_key = img_cfg.get("api_key", "")
    image_model = img_cfg.get("model", "gemini-2.0-flash")
    image_base_url = img_cfg.get("base_url", "https://generativelanguage.googleapis.com/v1beta/openai/")

    raw_exts = cfg.get('extensions', [])
    if isinstance(raw_exts, dict):
        default_ext_str = ','.join(k for k, v in raw_exts.items() if v)
    else:
        default_ext_str = ','.join(raw_exts)
    ext_input = input(f"Enter file extensions (comma-separated) [{default_ext_str}]: ").strip()
    ext_raw = ext_input or default_ext_str
    requested_extensions = {
        (e if e.startswith(".") else f".{e}")
        for ext in ext_raw.split(",")
        if (e := ext.strip().lower())
    }
    unsupported = requested_extensions - SUPPORTED_EXTENSIONS
    if unsupported:
        print(f"Warning: Ignoring unsupported extension(s): {', '.join(sorted(unsupported))}")
    supported_extensions = requested_extensions & SUPPORTED_EXTENSIONS
    if not supported_extensions:
        print("Error: No supported extensions selected. Exiting.")
        sys.exit(1)

    if {".jpg", ".jpeg", ".png"} & supported_extensions:
        # Prompt for image conversion settings
        resp = input("Enable image conversion (EXIF/OCR)? (y/n): ").strip().lower()
        image_conversion_enabled = resp == "y"
        if image_conversion_enabled:
            mode_resp = input("Image mode: (1) EXIF metadata only  (2) Full OCR: ").strip()
            image_mode = "ocr" if mode_resp == "2" else "exif"
            if image_mode == "ocr":
                provider_resp = input("LLM provider: (1) Gemini free tier  (2) Ollama local  (3) Custom: ").strip()
                image_provider = {"1": "gemini", "2": "ollama", "3": "custom"}.get(provider_resp, image_provider)
                # Provider preset table (duplicated literal dict):
                presets = {
                    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/", "gemini-2.0-flash"),
                    "ollama": ("http://localhost:11434/v1", "llava"),
                    "custom": ("", ""),
                }
                preset_base_url, preset_model = presets[image_provider]
                image_base_url = preset_base_url if image_provider != "custom" else input("Base URL: ").strip()
                image_model = input(f"Model name [{preset_model}]: ").strip() or preset_model
                if image_provider != "ollama":
                    image_api_key = input("API key (leave blank to keep existing): ").strip() or image_api_key
            else:  # EXIF mode
                # Check exiftool discoverability and warn (section 4 will add this logic)
                pass

    force_convert = input(f"Force convert all files? (y/n) [{'y' if cfg.get('force', False) else 'n'}]: ").strip().lower() or ('y' if cfg.get("force", False) else 'n')
    dry_run = input(f"Dry run only? (y/n) [{'y' if cfg.get('dry_run', False) else 'n'}]: ").strip().lower() or ('y' if cfg.get("dry_run", False) else 'n')
    logging_enabled = input(f"Enable logging? (y/n) [{'y' if cfg.get('logging', True) else 'n'}]: ").strip().lower() or ('y' if cfg.get("logging", True) else 'n')

    # ─── SAVE CONFIG ──────────────────────────────────────────────────────────
    save_config({
        "input_folder": str(input_folder),
        "output_folder": str(output_folder),
        "extensions": {ext: True for ext in supported_extensions},
        "force": force_convert == 'y',
        "dry_run": dry_run == 'y',
        "logging": logging_enabled == 'y',
        "image_conversion": {
            "enabled": image_conversion_enabled,
            "mode": image_mode,
            "provider": image_provider,
            "api_key": image_api_key,
            "model": image_model,
            "base_url": image_base_url,
        }
    })

    # ─── INITIALIZATION ───────────────────────────────────────────────────────
    md = MarkItDown()
    files_to_convert = []
    skipped = 0
    log_lines = []

    # ─── COLLECT FILES TO CONVERT ─────────────────────────────────────────────
    for root, _, files in os.walk(input_folder):
        for file in files:
            src_path = Path(root) / file
            if not is_safe_path(input_folder, src_path):
                print(f"Skipped (traversal): {src_path}")
                log_lines.append(f"[{datetime.now()}] Skipped (traversal): {src_path}")
                continue
            if src_path.suffix.lower() not in supported_extensions:
                continue

            rel_path = src_path.relative_to(input_folder)
            dst_path = output_folder / rel_path.with_suffix(".md")

            if not is_safe_path(output_folder, dst_path):
                print(f"Skipped (output traversal): {src_path}")
                log_lines.append(f"[{datetime.now()}] Skipped (output traversal): {src_path}")
                continue

            if dst_path.exists() and force_convert != 'y':
                if dst_path.stat().st_mtime >= src_path.stat().st_mtime:
                    skipped += 1
                    continue

            files_to_convert.append((src_path, dst_path))

    # ─── DRY RUN MODE ─────────────────────────────────────────────────────────
    if dry_run == 'y':
        print("\n=== DRY RUN SUMMARY ===")
        print(f"Files that would be converted: {len(files_to_convert)}")
        print(f"Files skipped (up-to-date): {skipped}")
        proceed = input("Proceed with actual conversion? (y/n): ").strip().lower()
        if proceed != 'y':
            sys.exit(0)

    # ─── CONVERSION ───────────────────────────────────────────────────────────
    converted = 0
    failed = 0
    total = len(files_to_convert)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_path = Path(LOGS_DIR) / f"conversion_log_{timestamp}.log"

    for i, (src_path, dst_path) in enumerate(files_to_convert, 1):
        try:
            result = md.convert(str(src_path))
            content = result.text_content or ""
            if not content.strip():
                print(f"[{i}/{total}] Skipped (empty output): {src_path.relative_to(input_folder)}")
                skipped += 1
                log_lines.append(f"[{datetime.now()}] Skipped (empty output): {src_path}")
            else:
                dst_path.parent.mkdir(parents=True, exist_ok=True)
                with open(dst_path, "w", encoding="utf-8") as f:
                    f.write(content)
                print(f"[{i}/{total}] Converted: {src_path.relative_to(input_folder)}")
                converted += 1
                log_lines.append(f"[{datetime.now()}] Converted: {src_path}")
        except Exception as e:
            print(f"[{i}/{total}] Error converting {src_path.name}: {e}")
            failed += 1
            log_lines.append(f"[{datetime.now()}] Error converting {src_path}: {e}")

    # ─── SUMMARY ──────────────────────────────────────────────────────────────
    print("\n=== CONVERSION SUMMARY ===")
    print(f"Converted: {converted}")
    print(f"Skipped  : {skipped}")
    print(f"Errors   : {failed}")

    if logging_enabled == 'y':
        try:
            with open(log_path, "w", encoding="utf-8") as log_file:
                header = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Lean Markdown Converter v{VERSION}\n"
                log_file.write(header)
                log_file.write("\n".join(log_lines))
        except Exception as e:
            print(f"Warning: Could not save log file: {e}")
        view = input("View log file? (y/n): ").strip().lower()
        if view == 'y':
            try:
                subprocess.Popen(["notepad.exe", str(log_path)])
            except Exception as e:
                print(f"Could not open log file: {e}")
