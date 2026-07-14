# Lean Markdown Converter 2.0.0

Batch convert 21 file formats to Markdown using [Microsoft MarkItDown](https://github.com/microsoft/markitdown). Choose between GUI (tkinter, drag - drop friendly) or CLI (interactive terminal prompts). Run locally on Windows with no account required.

## Features

- **Batch conversion** - point at a folder, convert all supported files at once
- **Smart skip logic** - skip already - converted files, dangerous extensions, empty inputs
- **Folder mirroring** - output preserves your source directory structure
- **Dry - run mode** - preview conversions before committing
- **Live file count** - GUI shows count updates as you adjust filters
- **Cancel anytime** - conversion runs in a background worker thread
- **Settings persistence** - your last folder, extensions, and options are remembered
- **Timestamped logs** - detailed logs per run in `%APPDATA%\LeanProductivity\logs\`

## Supported Formats (21)

CSV, DOC, DOCX, EPUB, HTM, HTML, IPYNB, JPEG, JPG, JSON, M4A, MP3, MSG, PDF, PNG, PPT, PPTX, WAV, XLS, XLSX, XML.

Note: Image formats (JPG, PNG) require an image conversion mode (see below). If unavailable, they are skipped with a warning.

## Image Conversion

Two independent modes - choose privacy - first or speed.

**EXIF mode (default, local)**: Extracts metadata using ExifTool. No API calls, no images sent anywhere. ExifTool is optional (installer component ~40 MB, or in system PATH). Missing ExifTool - file is skipped, no error.

**AI OCR mode**: Sends images to a provider for text extraction via OpenAI - compatible API. Choose:
- **Ollama (fully private)**: Run `ollama pull glm-ocr` locally. All images stay on your machine. Free, no API keys needed.
- **Gemini (online)**: Google's flash model. Requires API key. Privacy: images are sent to Google but deleted after processing.
- **Custom endpoint**: OpenAI or OpenAI - compatible. You control which provider handles the images.

Configure image conversion in the GUI settings or `conversion_config.json` (dev mode only; frozen app uses `%APPDATA%\LeanProductivity\config.json`).

## Audio Transcription

MP3, M4A, and WAV files are transcribed to text using Google's speech service (requires internet). The app uses ffmpeg and ffprobe to decode audio - both are included in the optional installer audio component (~226 MB), or sourced from your system PATH.

Note: M4A transcription was completely broken in v1.x due to a stdin - pipe limitation. v2.0.0 fixes this by pre - decoding M4A to WAV before transcription.

## Installation

### From Installer (Recommended)

1. Download `LeanMarkdownConverterSetup.exe` from [Releases](https://github.com/sdkasper/lean-markdown-converter/releases).
2. Run the installer. Check the components you want:
   - **Core** (required) - the app itself (~120 MB)
   - **Audio** (optional) - ffmpeg + ffprobe for MP3/M4A/WAV transcription (~226 MB)
   - **ExifTool** (optional, default - checked) - image metadata extraction (~40 MB)
3. Click Install. Shortcuts are created in your Start Menu.

**Upgrading from v1.x**: If you have v1 installed, the installer will preserve your settings. Keep the **Audio** component checked unless you don't need audio transcription.

### Portable (No Installer)

Download `LPMarkdownConverter.exe` from [Releases](https://github.com/sdkasper/lean-markdown-converter/releases) and run directly. Settings are stored in `%APPDATA%\LeanProductivity\config.json`. Audio/ExifTool must be in your system PATH.

## Build from Source

Requires Python 3.13+, Git LFS (for binary artifacts).

```bash
# Clone and setup
git clone https://github.com/sdkasper/lean-markdown-converter.git
cd lean-markdown-converter
pip install -r requirements.txt

# Run (dev mode)
python -m cli.main          # CLI - interactive prompts
python -m gui.main          # GUI - tkinter

# Test
pytest tests/               # 184 - test suite

# Build (PowerShell)
powershell build.ps1        # exe only -> dist/LPMarkdownConverter.exe
powershell build.ps1 -Installer   # exe + Inno Setup installer

# Verify build
dist/LPMarkdownConverter.exe --selftest    # must exit 0
```

## Architecture

Shared - core design: All conversion logic lives in `core/` (constants, config, binary discovery, LLM integration, file scanning, transcoding engine). `gui/` and `cli/` are thin presentation layers with zero duplicated logic. 9 modules total, 184 unit tests.

## License

See [LICENSE.txt](setup/LICENSE.txt) in the installer package or `setup/LICENSE.txt` in the source tree.

## Troubleshooting

- **Images skipped with warning**: ExifTool missing (dev mode) or OCR not configured. Run the installer with ExifTool component, or configure an OCR provider in settings.
- **Audio transcription hangs or fails**: Check ffmpeg/ffprobe are installed (installer audio component or system PATH). Run `ffmpeg -version` in terminal to verify.
- **Settings not persisting**: Frozen app stores config in `%APPDATA%\LeanProductivity\config.json`. Dev mode uses `conversion_config.json` in the project root.
- **Build fails on Windows**: Ensure PowerShell execution policy allows unsigned scripts: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`.

## Support

This is a single - user desktop tool maintained by Sascha at [LeanProductivity](https://leanproductivity.tv). Report issues on [GitHub](https://github.com/sdkasper/lean-markdown-converter/issues).
