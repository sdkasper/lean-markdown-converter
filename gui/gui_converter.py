# ─── APPLICATION METADATA ──────────────────────────────────────────────────
APP_NAME = "LeanProductivity MarkItDown Batch Converter no GUI"
APP_DESCRIPTION = "A no GUI batch converter for MarkItDown to convert various file formats to Markdown."
VERSION = "00.09.20250620"
AUTHOR_NAME = "Sascha D. Kasper - LeanProductivity"
HELP_URL = "https://github.com/microsoft/markitdown"
NOTE = "STILL NOT SUPPORTING MP3 AND M4A IN THE COMPILED APP VERSION DUE TO FFmpeg ISSUES."
# ──────────────────────────────────────────────────────────────────────────

import os
from pathlib import Path
from markitdown import MarkItDown

# --- Optional: FFMPEG path for audio support (if pydub or similar is used) ---
try:
    from pydub import AudioSegment
    ffmpeg_path = os.path.join("resources", "bin", "ffmpeg.exe")
    if not Path(ffmpeg_path).is_file():
        raise FileNotFoundError(f"FFmpeg not found at {ffmpeg_path}")
    AudioSegment.converter = ffmpeg_path
except ImportError:
    pass  # pydub not installed or not needed for current file types
except Exception as e:
    print(f"⚠️ FFmpeg configuration warning: {e}")

# --- Configuration ---
input_folder = Path(r"d:\GitProjects\Input\Demo Files")  # set this to your input folder
output_folder = Path(r"d:\GitProjects\Output")           # set this to your output folder

# --- Extension input from user ---
ext_input = input("Enter file extensions to convert (comma-separated, e.g. docx,pdf,html): ")
supported_extensions = {
    f".{ext.strip().lower()}"
    for ext in ext_input.split(",")
    if ext.strip()
}

force_convert = False  # Set to True to ignore modification times
dry_run = False        # Set to True to simulate conversion only

# --- Init ---
md = MarkItDown()
files_converted = 0
files_skipped = 0
errors = 0

# --- Conversion ---
for root, _, files in os.walk(input_folder):
    for file in files:
        src_path = Path(root) / file
        if src_path.suffix.lower() not in supported_extensions:
            continue

        rel_path = src_path.relative_to(input_folder)
        dst_path = output_folder / rel_path.with_suffix(".md")
        dst_path.parent.mkdir(parents=True, exist_ok=True)

        if dst_path.exists() and not force_convert:
            if dst_path.stat().st_mtime >= src_path.stat().st_mtime:
                print(f"⏭️  Skipped (up-to-date): {rel_path}")
                files_skipped += 1
                continue

        if dry_run:
            print(f"🔎 Would convert: {rel_path}")
            files_converted += 1
            continue

        try:
            # Build subprocess environment with additional PATH entries
            env = os.environ.copy()
            env["PATH"] = (
                os.path.abspath("resources/bin") + os.pathsep +
                os.getcwd() + os.pathsep +
                env["PATH"]
            )

            import subprocess
            result = subprocess.run(
                ["markitdown", str(src_path.resolve())],
                capture_output=True,
                text=True,
                check=True,
                env=env,
                cwd=os.getcwd()
            )

            with open(dst_path, "w", encoding="utf-8") as f:
                f.write(result.stdout)
            print(f"✅ Converted: {rel_path}")
            files_converted += 1

        except subprocess.CalledProcessError as e:
            print(f"❌ CLI failed for {rel_path}: {e.stderr.strip()}")
            errors += 1
        except Exception as e:
            print(f"❌ Error converting {rel_path}: {type(e).__name__} – {e}")
            errors += 1

# --- Summary ---
print("\n=== Conversion Summary ===")
print(f"Converted: {files_converted}")
print(f"Skipped  : {files_skipped}")
print(f"Errors   : {errors}")
