# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A batch file-to-Markdown converter using [Microsoft MarkItDown](https://github.com/microsoft/markitdown). Provides both a CLI (interactive terminal prompts) and a GUI (tkinter). Distributed as a Windows standalone `.exe` via PyInstaller + Inno Setup installer.

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
```

No test framework or linter is configured.

## Architecture

Two independent entry points share the same conversion approach (MarkItDown → `.md`) but do **not** share code — each has its own file-walking, config I/O, and conversion loop:

- **`gui/gui_converter.py`** — `FileConverterApp` class, tkinter UI, threaded conversion via `worker_thread()`. This is the PyInstaller entry point.
- **`terminal/cli_converter.py`** — Linear script with `input()` prompts, no classes.

Both read/write **`conversion_config.json`** (persisted user settings: folders, extension toggles, force/dry-run/logging flags). The GUI stores extensions as `{".pdf": true, ...}` dict; the CLI stores them as a list — the GUI handles both formats on load.

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

## Git & Deployment

- Git LFS tracks `*.exe` and `*.zip` (see `.gitattributes`)
- Remote: `sdkasper/lp-bulk-markdown-converter`
- Installer `.exe` lives in `setup/` (tracked via LFS)
- `Input/` and `Output/` contain test/demo files and are committed; `logs/` is gitignored
