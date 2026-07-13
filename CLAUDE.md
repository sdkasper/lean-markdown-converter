# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A batch file-to-Markdown converter using [Microsoft MarkItDown](https://github.com/microsoft/markitdown). Provides both a CLI (interactive terminal prompts) and a GUI (tkinter). Distributed as a Windows standalone `.exe` via PyInstaller + Inno Setup installer.

Current version: **v1.0.9** (Lean Markdown Converter)

## Commands

```bash
# Setup
pip install -r requirements.txt          # 55 pinned deps including markitdown[all], magika, pydub

# Run
python terminal/cli_converter.py         # CLI — interactive prompts for folders, extensions, options
python gui/gui_converter.py              # GUI — tkinter interface

# Build (PowerShell)
powershell build.ps1                     # Runs: pyinstaller LPMarkdownConverter.spec
                                         # Produces single-file .exe in dist/

# Test
pytest tests/                            # Run all tests (comprehensive suite in tests/)
pytest tests/test_conversion_flow.py     # Run specific test file
```

Linter: None configured. Format with your preferred tool (black, ruff, etc.).

## Architecture

Two independent entry points share the same conversion approach (MarkItDown → `.md`) but do **not** share code — each has its own file-walking, config I/O, and conversion loop:

- **`gui/gui_converter.py`** — `FileConverterApp` class, tkinter UI, threaded conversion via `worker_thread()`. This is the PyInstaller entry point.
- **`terminal/cli_converter.py`** — Linear script with `input()` prompts, no classes.

Both read/write **`conversion_config.json`** (persisted user settings: folders, extension toggles, force/dry-run/logging flags). The GUI stores extensions as `{".pdf": true, ...}` dict; the CLI stores them as a list — the GUI handles both formats on load.

### Supported Formats

`.csv` `.doc` `.docx` `.epub` `.htm` `.html` `.ipynb` `.jpeg` `.jpg` `.json` `.m4a` `.mp3` `.msg` `.pdf` `.png` `.ppt` `.pptx` `.wav` `.xls` `.xlsx` `.xml`

**Note:** `.bmp`, `.gif`, and `.tiff` are NOT supported. MarkItDown's `ImageConverter` only accepts `.jpg`/`.jpeg`/`.png` by extension (or `image/jpeg`/`image/png` by mimetype) — verified directly against the installed package for both markitdown 0.1.5 and the latest 0.1.6. Selecting a `.bmp`/`.gif`/`.tiff` file raises `UnsupportedFormatException` on every conversion attempt (a 100% failure rate, not a silent empty output), so they're deliberately excluded from `SUPPORTED_EXTENSIONS`. Re-adding them would require an upstream MarkItDown change.

### Image Support

Re-enabled for `.jpg`/`.jpeg`/`.png` (previously removed entirely). MarkItDown's `ImageConverter` supports two independent layers, both triggered automatically by `MarkItDown().convert(...)` — no code changes are needed beyond including the extension in the allowlist:

- **Basic (EXIF metadata) — no LLM required, but needs the `exiftool` binary.** MarkItDown auto-detects `exiftool` via the `EXIFTOOL_PATH` env var or well-known system install locations (e.g. `C:\Program Files`, `/usr/local/bin`) at `MarkItDown()` construction time; it is **not** currently bundled with this app (unlike `ffmpeg`, which is bundled for audio). If `exiftool` isn't found, image conversion still succeeds but returns empty text content — the existing "skip empty output" logic in both CLI and GUI will then treat the file as skipped rather than converted. Install exiftool and ensure it's discoverable (env var or standard path) to get metadata like `ImageSize`, `DateTimeOriginal`, `GPSPosition`, etc.
- **Advanced (LLM OCR/description) — optional, requires wiring.** Passing `llm_client` and `llm_model` (and optionally `llm_prompt`) to the `MarkItDown(...)` constructor makes the `ImageConverter` call the client's `chat.completions.create(...)` (OpenAI-compatible) to generate a `# Description:` section. **Neither `gui/gui_converter.py` nor `terminal/cli_converter.py` currently passes these kwargs** — both instantiate `MarkItDown()` with no arguments, so today only the EXIF-metadata path is active. Adding a settings field for an API key/model and passing it through to the `MarkItDown()` constructor is a separate follow-up if LLM-based descriptions are wanted.

### Key files

| File | Purpose |
|------|---------|
| `LPMarkdownConverter.spec` | PyInstaller spec — bundles `gui_converter.py`, ffmpeg, magika models, icon |
| `hide_console.py` | PyInstaller runtime hook — patches `subprocess.Popen` with `CREATE_NO_WINDOW` to suppress console flashes in windowed mode |
| `build.ps1` | One-liner that invokes `pyinstaller LPMarkdownConverter.spec` |
| `setup/LPMarkdownConverterSetup.iss` | Inno Setup script for Windows installer |
| `resources/bin/ffmpeg.exe` | Bundled FFmpeg for audio conversion (mp3/m4a/wav via pydub) |
| `resources/LeanProductivity.ico` | App icon |

### Conversion flow

1. Walk `input_folder` recursively, filter by selected extensions
2. Mirror directory structure under `output_folder`, changing suffix to `.md`
3. Skip files where output already exists and is newer (unless force mode)
4. Call `MarkItDown().convert(src_path)` → write `result.text_content` to destination
5. Log results to timestamped file in `logs/`

### Config format (`conversion_config.json`)

GUI writes extensions as `{".ext": bool}` dict. CLI writes as `[".ext", ...]` list. The GUI's `load_config()` handles both formats; keep this backward compatibility if modifying config handling.

### Audio Support

CLI and GUI both configure pydub's `AudioSegment.converter` and `AudioSegment.ffprobe` to point to the bundled FFmpeg (or system path in compiled .exe). M4A support requires both `converter` AND `ffprobe` to be set (ffprobe detects the container format).

## Git & Deployment

- Git LFS tracks `*.exe` and `*.zip` (see `.gitattributes`)
- Remote: `sdkasper/lean-markdown-converter`
- Built artifacts live in `dist/` (exe) and `setup/` (installer), both tracked via LFS
- `Input/` and `Output/` contain demo/test files (committed); `logs/` is gitignored
- Releases published to GitHub with both standalone exe and installer
