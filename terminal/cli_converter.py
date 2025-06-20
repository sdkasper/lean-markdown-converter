# ─── APPLICATION METADATA ──────────────────────────────────────────────────
APP_NAME = "LeanProductivity MarkItDown Batch Converter no GUI"
APP_DESCRIPTION = "A no GUI batch converter for MarkItDown to convert various file formats to Markdown."
VERSION = "01.00.20250620"
AUTHOR_NAME = "Sascha D. Kasper - LeanProductivity"
HELP_URL = "https://github.com/microsoft/markitdown"
NOTE = "STILL NOT SUPPORTING MP3 AND M4A IN THE COMPILED APP VERSION DUE TO FFmpeg ISSUES."
# ──────────────────────────────────────────────────────────────────────────

import os
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime
from markitdown import MarkItDown

# ─── CONFIGURATION AND PATHS ──────────────────────────────────────────────
CONFIG_FILE = "conversion_config.json"
LOGS_DIR = "logs"
os.makedirs(LOGS_DIR, exist_ok=True)

# Optional: FFmpeg for audio support via pydub
try:
    from pydub import AudioSegment
    ffmpeg_path = os.path.join("resources", "bin", "ffmpeg.exe")
    if not Path(ffmpeg_path).is_file():
        raise FileNotFoundError(f"FFmpeg not found at {ffmpeg_path}")
    AudioSegment.converter = ffmpeg_path
except ImportError:
    pass  # pydub not installed
except Exception as e:
    print(f"⚠️ FFmpeg configuration warning: {e}")

# ─── LOAD OR PROMPT CONFIG ────────────────────────────────────────────────
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)

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
                    print(f"❌ Failed to create directory: {e}")

cfg = load_config()
input_folder = Path(prompt_path("Enter input folder path", cfg.get("input_folder")))
output_folder = Path(prompt_path("Enter output folder path", cfg.get("output_folder")))

ext_input = input(f"Enter file extensions (comma-separated) [{','.join(cfg.get('extensions', []))}]: ").strip()
ext_raw = ext_input or ','.join(cfg.get("extensions", []))
supported_extensions = {
    f".{ext.strip().lower()}"
    for ext in ext_raw.split(",")
    if ext.strip()
}

force_convert = input(f"Force convert all files? (y/n) [{'y' if cfg.get('force', False) else 'n'}]: ").strip().lower() or ('y' if cfg.get("force", False) else 'n')
dry_run = input(f"Dry run only? (y/n) [{'y' if cfg.get('dry_run', False) else 'n'}]: ").strip().lower() or ('y' if cfg.get("dry_run", False) else 'n')
logging_enabled = input(f"Enable logging? (y/n) [{'y' if cfg.get('logging', True) else 'n'}]: ").strip().lower() or ('y' if cfg.get("logging", True) else 'n')

# ─── SAVE CONFIG ──────────────────────────────────────────────────────────
save_config({
    "input_folder": str(input_folder),
    "output_folder": str(output_folder),
    "extensions": list(supported_extensions),
    "force": force_convert == 'y',
    "dry_run": dry_run == 'y',
    "logging": logging_enabled == 'y'
})

# ─── INITIALIZATION ───────────────────────────────────────────────────────
md = MarkItDown()
files_to_convert = []
skipped = 0

# ─── COLLECT FILES TO CONVERT ─────────────────────────────────────────────
for root, _, files in os.walk(input_folder):
    for file in files:
        src_path = Path(root) / file
        if src_path.suffix.lower() not in supported_extensions:
            continue

        rel_path = src_path.relative_to(input_folder)
        dst_path = output_folder / rel_path.with_suffix(".md")
        dst_path.parent.mkdir(parents=True, exist_ok=True)

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
log_lines = []
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
log_path = Path(LOGS_DIR) / f"conversion_log_{timestamp}.log"

for src_path, dst_path in files_to_convert:
    try:
        result = md.convert(str(src_path))
        with open(dst_path, "w", encoding="utf-8") as f:
            f.write(result.text_content)
        print(f"✅ Converted: {src_path.relative_to(input_folder)}")
        converted += 1
        log_lines.append(f"[{datetime.now()}] ✅ Converted: {src_path}")
    except Exception as e:
        print(f"❌ Error converting {src_path.name}: {e}")
        failed += 1
        log_lines.append(f"[{datetime.now()}] ❌ Error converting {src_path}: {e}")

# ─── SUMMARY ──────────────────────────────────────────────────────────────
print("\n=== CONVERSION SUMMARY ===")
print(f"Converted: {converted}")
print(f"Skipped  : {skipped}")
print(f"Errors   : {failed}")

if logging_enabled == 'y':
    with open(log_path, "w", encoding="utf-8") as log_file:
        log_file.write("\n".join(log_lines))
    view = input("View log file? (y/n): ").strip().lower()
    if view == 'y':
        try:
            os.startfile(str(log_path))
        except Exception as e:
            print(f"❌ Could not open log file: {e}")