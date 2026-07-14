# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A batch file-to-Markdown converter using [Microsoft MarkItDown](https://github.com/microsoft/markitdown). Provides both a CLI (interactive terminal prompts) and a GUI (tkinter). Distributed as a Windows standalone `.exe` via PyInstaller + Inno Setup installer.

Current version: **2.0.1** (Lean Markdown Converter) - a from-scratch rebuild with a shared `core/` package replacing the previous duplicated CLI/GUI architecture. Spec artifacts (9 EPICs, 31 user stories, 8 test cases, 6 NFRs) live in the vault at `$VAULT_PATH\01 Projects\LP Products\Lean Markdown Converter`.

## Commands

```bash
# Setup
pip install -r requirements.txt          # pinned deps incl. markitdown[all], magika, pydub, openai

# Run (dev mode)
python -m cli.main                       # CLI - interactive prompts for folders, extensions, options
python -m gui.main                       # GUI - tkinter interface
python -m gui.main --selftest            # frozen-bundle diagnostic (also works in dev); writes selftest_report.json

# Test
pytest tests/                            # full suite
pytest tests/core/                       # core logic only (fast)
pytest -m "not slow"                     # skip audio-heavy tests

# Build (PowerShell)
powershell build.ps1                     # PyInstaller exe only -> dist/LPMarkdownConverter.exe
powershell build.ps1 -Installer         # exe + staged exiftool + Inno Setup installer

# ALWAYS after building:
dist/LPMarkdownConverter.exe --selftest  # must exit 0; report at %APPDATA%\LeanProductivity\selftest_report.json
```

Linter: None configured. Format with your preferred tool (black, ruff, etc.).

## Architecture (v2.0.0)

Shared-core design: ALL logic lives in `core/`; `gui/` and `cli/` are thin presentation layers. Never duplicate logic into a UI layer.

| Module | Responsibility |
|--------|----------------|
| `core/constants.py` | APP_NAME, VERSION, 21-extension allowlist (`SUPPORTED_EXTENSIONS`), `EXT_GROUPS`, audio/image subsets |
| `core/paths.py` | frozen/dev path resolution (`config_file_path`, `logs_dir`, `exe_dir`), `is_safe_path` (NFR-001) |
| `core/config.py` | `ConverterConfig` dataclass, never-raise `load_config`, legacy list + missing-key backward compat |
| `core/binaries.py` | tool discovery (PATH > env var > `<exe_dir>\tools\` > dev `resources/bin/`), `configure_pydub` (both-or-neither), startup diagnostics |
| `core/llm_factory.py` | `PROVIDER_PRESETS`, `build_markitdown(image_conversion)` - single openai-SDK path for all providers |
| `core/scanner.py` | `collect_files` (walk, mirror, skip, safety), `count_files` (GUI live preview) |
| `core/engine.py` | `run_conversion` - per-file error boundary, empty-output guard, cancel semantics, audio counters |
| `core/logging_util.py` | `RunLogger` (timestamped logs), `format_summary`. API keys are NEVER logged |
| `gui/app.py` | `FileConverterApp` - widgets, worker thread + `root.after` updates, debounced live count |
| `gui/main.py` | PyInstaller entry point + `--selftest` diagnostic |
| `cli/main.py` | interactive prompt flow, dry-run confirm gate, Ctrl+C -> exit 130 |

Error contract: construction errors (`LLMConfigError`, bad folders) surface BEFORE any file is touched; per-file conversion errors are caught, counted, logged, and the run continues.

### Supported Formats (21)

`.csv` `.doc` `.docx` `.epub` `.htm` `.html` `.ipynb` `.jpeg` `.jpg` `.json` `.m4a` `.mp3` `.msg` `.pdf` `.png` `.ppt` `.pptx` `.wav` `.xls` `.xlsx` `.xml`

`.bmp`/`.gif`/`.tiff` are NOT supported - MarkItDown's `ImageConverter` only accepts jpg/jpeg/png; re-adding them requires an upstream MarkItDown change. Dangerous extensions (`.exe`, `.dll`, `.ps1`, `.bat`, `.zip`) must never enter the allowlist (NFR-002; enforced by `tests/core/test_extensions.py`).

### Image Support

Two independent layers selected via the `image_conversion` config block:

- **EXIF mode** (default): `MarkItDown()` with no LLM; requires the exiftool binary (optional installer component -> `{app}\tools\exiftool\`; discovered via PATH > `EXIFTOOL_PATH` > install dir). Missing exiftool -> empty output -> file skipped by the empty-output guard, with a UI warning.
- **OCR mode**: `MarkItDown(llm_client=openai.OpenAI(...), llm_model=...)`. All three providers (gemini/ollama/custom) use the plain openai SDK - Gemini via its OpenAI-compatible endpoint. `google-generativeai` was removed in v2.0.0; do not reintroduce it.

| provider | base_url | default model | API key |
|---|---|---|---|
| gemini | `https://generativelanguage.googleapis.com/v1beta/openai/` | `gemini-flash-latest` | required |
| ollama | `http://localhost:11434/v1` | `glm-ocr` | no (placeholder "ollama" sent) |
| custom | blank (user-supplied) | blank (user-supplied) | usually |

**Generation caps (do not remove, provider-aware):** `_apply_generation_caps` in `core/llm_factory.py` injects caps into every OCR request (MarkItDown passes none). Without a token cap, small local models fall into repetition loops on dense document pages - observed live with glm-ocr: ~1,500 lines of progressively corrupted garbage from one academic paper page. Per provider:

- `max_tokens=4096` - ALL providers. Bounds runaway loops and worst-case cloud token costs.
- `frequency_penalty=0.4` - ollama + custom ONLY. Gemini's OpenAI-compatible endpoint rejects the field with 400 INVALID_ARGUMENT (observed live 2026-07-14; it failed every image on that provider).
- `extra_body={"reasoning_effort": "none"}` - ollama ONLY. Thinking models (qwen3.5) route output to a hidden reasoning channel that counts against max_tokens; on dense pages they exhaust the whole budget thinking and return EMPTY content (observed live: finish_reason=length, 4096 completion tokens, 19k chars of reasoning, content ""). Non-thinking models (glm-ocr) ignore the field.

**Empty-description guard:** `core/engine.py::_ocr_description_body` - when OCR mode is active for an image and the output's `# Description:` section is empty or missing, the file is counted as failed with a log hint (EXIF metadata alone would otherwise make it look like a success). Regression-guarded by `TestEmptyDescriptionGuard`.

**Transcription prompt (2.0.1):** MarkItDown's built-in ImageConverter prompt ("Write a detailed caption for this image.") makes vision models paraphrase instead of transcribe. `DEFAULT_LLM_PROMPT` in `core/llm_factory.py` overrides it with a verbatim-transcription instruction, passed as `md.convert(path, llm_prompt=...)` by `core/engine.py` ONLY for files in `IMAGE_EXTENSIONS` and only when OCR mode is active (`resolve_llm_prompt` returns None otherwise) - embedded images in .docx/.pptx keep default captioning. Optional config override: `image_conversion.llm_prompt` (config-file-only, no GUI widget; empty/missing = default; the GUI carries the key through saves). Legacy configs without the key load unchanged.

**Local model guidance:** `glm-ocr` (default, ~2 GB) is the best local transcriber tested - excellent for screenshots, slides, and simple documents; dense multi-column pages can still trigger benign repetition until the token cap. `qwen3.5:9b` works (the reasoning kill-switch prevents empty output) but transcribes dense pages only partially. `gemma4` is NOT usable for OCR via Ollama - its vision path downscales images so aggressively (349 prompt tokens vs qwen's 3,125 for the same page) that it reports dense pages as "blank". For dense/academic pages, the Gemini provider is the reliable answer (verified: complete verbatim transcription incl. rotated margin text).

`image_conversion.api_key` is stored in plaintext in the config (accepted risk, single-user desktop tool) - never commit a populated config, never log the key.

### Audio Support

pydub needs BOTH `AudioSegment.converter` (ffmpeg) and `AudioSegment.ffprobe` (ffprobe) - M4A container detection requires ffprobe specifically. Binaries are NOT embedded in the exe (v2.0.0): they ship as the default-checked "audio" installer component -> `{app}\tools\`, with system PATH checked first and dev fallback `resources/bin/`. When unavailable, the GUI greys out the Audio group.

**M4A stdin-pipe workaround (do not remove):** MarkItDown feeds M4A streams to ffmpeg via a stdin pipe; MP4 containers keep their index (moov atom) at the file's end, which pipes cannot seek to, so ffmpeg silently yields 0.00s of audio and transcription fails with `UnknownValueError` on every non-faststart M4A (i.e., most of them, including iPhone voice memos). `core/engine.py::_m4a_to_temp_wav` pre-decodes .m4a by PATH into a temp WAV and hands that to MarkItDown. Trade-off: M4A metadata tags are not carried over (transcript-only output). Regression-guarded by `tests/core/test_engine.py::TestM4aPipeWorkaround` incl. a real speech fixture (`tests/fixtures/speech.m4a`).

### Config format (`conversion_config.json`)

Dev: project root. Frozen: `%APPDATA%\LeanProductivity\config.json`. Extensions stored as `{".ext": bool}` dict; legacy `[".ext"]` list still loads. Missing `image_conversion` key = feature off (pre-v1.1.0 configs load unchanged). See `core/config.py` `DEFAULT_IMAGE_CONVERSION`.

## Packaging (critical lessons)

- **`hide_console.py` must install a `subprocess.Popen` SUBCLASS, not a wrapper function.** `asyncio.windows_utils` subclasses `subprocess.Popen` at import time; a function there raises `TypeError: function() argument 'code' must be code, not str`. This single line blocked five v1.1.0 builds (openai imports asyncio; runtime hooks only run frozen). Do not "simplify" it back.
- **UPX stays off** in the spec until stability is re-proven with an explicit exclusion list.
- The spec bundles NO external binaries and only the icon from `resources/` - bundling the whole `resources/` folder would drag 226 MB of ffmpeg back in.
- `collect_submodules` for openai/httpx/pydantic/markitdown + certifi data are required for the frozen openai path.
- After every build run `dist\LPMarkdownConverter.exe --selftest` (exit 0, 8/8 PASS) before any manual testing.

## Key files

| File | Purpose |
|------|---------|
| `LPMarkdownConverter.spec` | PyInstaller spec - entry `gui/main.py`, upx=False, no embedded binaries |
| `hide_console.py` | Runtime hook - `_NoWindowPopen` subclass (see Packaging above) |
| `build.ps1` | Build pipeline: exe, magika bundle check, `-Installer` stages exiftool zip + runs iscc |
| `setup/LeanMarkdownConverterSetup.iss` | Inno Setup - components: core (fixed) / audio / exiftool (default-checked) |
| `resources/bin/ffmpeg.exe`, `ffprobe.exe` | Installer audio component sources (Git LFS) |
| `resources/bin/exiftool-13.59.zip` | Installer exiftool component source, extracted by build.ps1 to `setup/staging/` (Git LFS) |
| `resources/LeanProductivity.ico` | App icon (only resource embedded in the exe) |

## Git & Deployment

- Git LFS tracks `*.exe` and `*.zip` (`.gitattributes`)
- Remote: `sdkasper/lean-markdown-converter`; v2.0.0 rebuild lives on the `work` branch
- Built artifacts: `dist/` (exe) and `setup/` (installer), both LFS
- `Input/`/`Output/` contain demo files (committed); `logs/`, `setup/staging/`, `selftest_report.json` gitignored
- Release: build both artifacts (`build.ps1 -Installer`), selftest, commit via LFS, tag, publish to GitHub Releases
- Tag/version convention (since 2.0.0): NO "v" prefix anywhere - tags are plain `2.0.0`, and the app displays "Lean Markdown Converter 2.0.0" (window title, CLI banner, log header). Legacy v-prefixed tags (v1.0.x and older) remain untouched.
