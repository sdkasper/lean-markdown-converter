# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A batch file-to-Markdown converter using [Microsoft MarkItDown](https://github.com/microsoft/markitdown). Provides both a CLI (interactive terminal prompts) and a GUI (tkinter). Distributed as a Windows standalone `.exe` via PyInstaller + Inno Setup installer.

Current version: **v1.1.0** (Lean Markdown Converter)

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

Re-enabled for `.jpg`/`.jpeg`/`.png` (previously removed entirely). MarkItDown's `ImageConverter` supports two independent layers — EXIF metadata (no LLM) and LLM-based OCR/description — selected per-run via the `image_conversion` config block (see "Config format" below) rather than always defaulting to the bare EXIF path.

**Master toggle + mode choice.** `image_conversion.enabled` is the master switch; when off, `.jpg`/`.jpeg`/`.png` files still show as selectable extensions but conversion falls back to `MarkItDown()` with no LLM wiring (EXIF-only, same as pre-v1.1.0 behavior). When `enabled` is true, `image_conversion.mode` picks the layer: `"exif"` (default, no LLM) or `"ocr"` (LLM vision call via an OpenAI-compatible client). In the GUI, the master toggle greys out (but does not uncheck) the `.jpg`/`.jpeg`/`.png` extension checkboxes and the "Images" group-checkbox when off, so re-enabling restores the user's prior selection.

- **EXIF mode — no LLM required, but needs the `exiftool` binary.** MarkItDown auto-detects `exiftool` via the `EXIFTOOL_PATH` env var or well-known system install locations at `MarkItDown()` construction time. If `exiftool` isn't found, image conversion still succeeds but returns empty text content — the existing "skip empty output" logic in both CLI and GUI treats the file as skipped rather than converted, and both surfaces show a warning when EXIF mode is selected and exiftool can't be located (checked via `shutil.which("exiftool")`, then a bundled-copy fallback).
- **OCR mode — LLM vision call, provider-selectable.** `image_conversion.provider` picks one of three presets, each supplying a default `base_url`/`model` (user-editable) that get passed through an OpenAI-compatible client into `MarkItDown(llm_client=..., llm_model=...)`:

  | provider | base_url | default model | API key required |
  |---|---|---|---|
  | gemini | `https://generativelanguage.googleapis.com/v1beta/openai/` | `gemini-2.0-flash` | yes |
  | ollama | `http://localhost:11434/v1` | `llava` | no (local server; a placeholder string is sent since the OpenAI SDK requires a non-empty `api_key`) |
  | custom | blank (falls through to official `api.openai.com` if left blank) | blank (user-supplied, e.g. `gpt-4o`) | yes, typically |

- **exiftool packaging.** Unlike `ffmpeg` (bundled into the frozen exe for audio), `exiftool` is **not** embedded in the single-file PyInstaller build — it ships as an **optional Windows installer component** (Inno Setup task, checked by default) so users can decline it. The dev-script path (`python gui/gui_converter.py`) relies entirely on PATH/`EXIFTOOL_PATH` discovery with no bundled fallback.
- **No new binary for OCR mode.** The `openai` package (added to `requirements.txt`) is pure-Python, so OCR mode requires no additional bundled binary — only the network-facing HTTP client.
- **API key storage caveat.** `image_conversion.api_key` is stored **in plaintext** in `conversion_config.json` (masked in the GUI display field, but not encrypted at rest). This matches the app's existing security posture — there is no encryption anywhere in this codebase, and it's a single-user desktop tool — but it means the config file must never be committed or shared once populated with a real key (see `.gitignore` note below). Never log the API key value in any log line.

### Key files

| File | Purpose |
|------|---------|
| `LPMarkdownConverter.spec` | PyInstaller spec — bundles `gui_converter.py`, ffmpeg, magika models, icon |
| `hide_console.py` | PyInstaller runtime hook — patches `subprocess.Popen` with `CREATE_NO_WINDOW` to suppress console flashes in windowed mode |
| `build.ps1` | One-liner that invokes `pyinstaller LPMarkdownConverter.spec` |
| `setup/LPMarkdownConverterSetup.iss` | Inno Setup script for Windows installer |
| `resources/bin/ffmpeg.exe` | Bundled FFmpeg for audio conversion (mp3/m4a/wav via pydub) |
| `resources/bin/exiftool.exe` | Optional Windows installer component, not embedded in the frozen single-file exe |
| `resources/LeanProductivity.ico` | App icon |

### Conversion flow

1. Walk `input_folder` recursively, filter by selected extensions
2. Mirror directory structure under `output_folder`, changing suffix to `.md`
3. Skip files where output already exists and is newer (unless force mode)
4. Call `MarkItDown().convert(src_path)` → write `result.text_content` to destination
5. Log results to timestamped file in `logs/`

### Config format (`conversion_config.json`)

GUI writes extensions as `{".ext": bool}` dict. CLI writes as `[".ext", ...]` list. The GUI's `load_config()` handles both formats; keep this backward compatibility if modifying config handling.

Since v1.1.0, both files also read/write a top-level `image_conversion` object:

```json
"image_conversion": {
    "enabled": false,
    "mode": "exif",
    "provider": "gemini",
    "api_key": "",
    "model": "gemini-2.0-flash",
    "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/"
}
```

This key is **optional and defaults to disabled** — old `conversion_config.json` files written before v1.1.0 have no `image_conversion` key at all, and both `load_config()` functions treat its absence as "feature off, EXIF-only fallback" via chained `.get("image_conversion", {}).get(field, default)` lookups. No migration code is needed.

### Audio Support

CLI and GUI both configure pydub's `AudioSegment.converter` and `AudioSegment.ffprobe` to point to the bundled FFmpeg (or system path in compiled .exe). M4A support requires both `converter` AND `ffprobe` to be set (ffprobe detects the container format).

## Git & Deployment

- Git LFS tracks `*.exe` and `*.zip` (see `.gitattributes`)
- Remote: `sdkasper/lean-markdown-converter`
- Built artifacts live in `dist/` (exe) and `setup/` (installer), both tracked via LFS
- `Input/` and `Output/` contain demo/test files (committed); `logs/` is gitignored
- Releases published to GitHub with both standalone exe and installer
