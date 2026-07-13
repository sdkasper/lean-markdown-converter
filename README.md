
# Lean Markdown Converter

Batch convert various file formats to Markdown using [Microsoft MarkItDown](https://github.com/microsoft/markitdown). Provides both a **CLI** (interactive terminal) and a **GUI** (tkinter) for technical and non-technical users alike.

## 🖥️ Windows Standalone App

A Windows 11 standalone installer is available — no Python, Git, or additional dependencies required. Everything (Magika models, FFmpeg, etc.) is bundled into a single EXE.

**Download:** [https://kspr.me/bulkmd](https://kspr.me/bulkmd)

Run `LPMarkdownConverterSetup.exe` and follow the prompts to install. Launch via **Start Menu > Lean Markdown Converter** or use the optional desktop shortcut.

## 📦 Supported Formats

`.csv` `.doc` `.docx` `.epub` `.htm` `.html` `.ipynb` `.jpeg` `.jpg` `.json` `.m4a` `.mp3` `.msg` `.pdf` `.png` `.ppt` `.pptx` `.wav` `.xls` `.xlsx` `.xml`

Audio formats (`.mp3`, `.m4a`, `.wav`) require FFmpeg — bundled in `resources/bin/ffmpeg.exe` for the standalone app.

Images (`.jpg`, `.jpeg`, `.png`) are converted to Markdown containing EXIF metadata (image size, date taken, GPS position, etc.), if the [`exiftool`](https://exiftool.org/) binary is installed and discoverable (via the `EXIFTOOL_PATH` environment variable or a standard system install location) — it is not currently bundled with this app. Without exiftool, images still convert without erroring but produce empty output, which the converter reports as "skipped." MarkItDown also supports LLM-generated image descriptions (OCR/captioning) via an optional `llm_client`/`llm_model`, but that isn't wired into the CLI/GUI settings yet. `.bmp`, `.gif`, and `.tiff` are not supported — MarkItDown's image converter only accepts `.jpg`/`.jpeg`/`.png`.

## 🔧 Setup (from source)

```bash
# Clone the repository
git clone https://github.com/sdkasper/lp-bulk-markdown-converter.git
cd lp-bulk-markdown-converter

# Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

# Install dependencies
pip install -r requirements.txt
```

**Requirements:** Python 3.13+, pip

## ▶️ Usage

### CLI Script

```bash
python terminal/cli_converter.py
```

You will be prompted to:
- Enter input/output folders
- Choose which file types to convert (comma-separated)
- Enable/disable logging, dry run, and force conversion

### GUI Script

```bash
python gui/gui_converter.py
```

- Browse and select your input/output folders
- Use checkboxes to select file types
- Enable dry run, logging, and force conversion with simple toggles
- A progress bar shows conversion status

Both modes save preferences automatically in `conversion_config.json`.

### 🧰 How the Scripts Differ

| Feature              | CLI (`terminal/cli_converter.py`)  | GUI (`gui/gui_converter.py`)       |
|----------------------|------------------------------------|-------------------------------------|
| Interface            | Text-based, terminal prompts       | Full graphical interface            |
| Dependencies         | Python only                        | Requires `tkinter`                  |
| Use case             | Developers / Power users           | Non-technical users                 |
| Automation-friendly  | ✅ Yes                              | ❌ Manual input only                |

## 🏗️ Build

Build the standalone Windows `.exe` with PyInstaller:

```powershell
# PowerShell
.\build.ps1
```

This runs `pyinstaller LPMarkdownConverter.spec`, producing `dist/LPMarkdownConverter.exe`. The spec file bundles `gui/gui_converter.py` as the entry point along with FFmpeg, Magika models, the app icon, and a runtime hook (`hide_console.py`) to suppress console windows.

To create the Windows installer, open `setup/LPMarkdownConverterSetup.iss` in [Inno Setup](https://jrsoftware.org/isinfo.php) and compile.

## ✅ Testing & CI/CD

The project includes a comprehensive test suite (141 tests) with GitHub Actions CI/CD integration:

- **Tests run on:** Python 3.11 and 3.13 (automated on every push)
- **Test framework:** pytest
- **Coverage:** 26.56% of codebase
- **Pass rate:** 99.1%

Run tests locally with:

```bash
pytest tests/
```

View the full release notes and test results: [GitHub Releases](https://github.com/sdkasper/lean-markdown-converter/releases)

## 📁 Project Structure

```
├── terminal/cli_converter.py    # CLI entry point
├── gui/gui_converter.py         # GUI entry point (PyInstaller target)
├── conversion_config.json       # Persisted user settings
├── hide_console.py              # PyInstaller runtime hook
├── LPMarkdownConverter.spec     # PyInstaller build spec
├── build.ps1                    # Build script
├── requirements.txt             # Pinned Python dependencies
├── resources/
│   ├── bin/ffmpeg.exe           # Bundled FFmpeg for audio support
│   ├── LeanProductivity.ico     # App icon
│   └── logo.png                 # Logo
├── setup/
│   ├── LPMarkdownConverterSetup.iss   # Inno Setup installer script
│   └── LPMarkdownConverterSetup.exe   # Compiled installer (Git LFS)
├── logs/                        # Conversion session logs
├── Input/                       # Demo/test input files
└── Output/                      # Demo/test output files
```

## 📄 License

This project is licensed under the [MIT License](LICENSE.md).

## 🙋‍♂️ Author

Created by **Sascha D. Kasper** – [LeanProductivity](https://sascha-kasper.com)

Tutorial: [https://youtu.be/vvZ11rPff14](https://youtu.be/vvZ11rPff14)
