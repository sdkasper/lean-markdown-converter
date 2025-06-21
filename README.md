
# LeanProductivity MarkItDown Batch Converter

This repository contains two Python-based tools for **batch converting various file formats to Markdown** using [Microsoft MarkItDown](https://github.com/microsoft/markitdown). It's designed for both technical and non-technical users who need to process multiple files efficiently.

## 🖥️ Windows Standalone App
I also provide a Windows 11 standalone installer - no Python, Git, or additional dependencies are required. Everything (Magika models, FFmpeg, etc.) is bundled into a single EXE. You can download it here: https://kspr.me/bulkmd

Run LPMarkdownConverterSetup.exe and follow the prompts to install.

Launch via Start Menu > LeanProductivity Markdown Converter or use the optional desktop shortcut.

## Scripts
### 📦 What's Included

| Script                          | Description                                                  |
|---------------------------------|--------------------------------------------------------------|
| `cli_converter.py`              | Terminal-based converter with interactive prompts (no GUI)  |
| `gui_converter.py`              | Graphical interface for selecting folders and options       |
| `conversion_config.json`        | Automatically created to remember user settings             |
| `resources/bin/ffmpeg.exe`      | (Optional) For audio file support with pydub                |
| `logs/`                         | Logs for each conversion session                            |

Both tools support `.docx`, `.pdf`, `.html`, `.json`, `.xml`, `.txt`, `.jpg`, `.png`, `.csv`, and many more.

### 🧰 How the Scripts Differ

| Feature               | `cli_converter.py`              | `gui_converter.py`            |
|----------------------|----------------------------------|--------------------------------|
| Interface            | Text-based, terminal prompts     | Full graphical interface       |
| Dependencies         | Python only                      | Requires `tkinter`             |
| Use case             | Developers / Power users         | Non-technical users            |
| Automation-friendly  | ✅ Yes                            | ❌ Manual input only           |

### ▶️ How to Use: CLI Script
```bash
python cli_converter.py
```
🛠 You will be prompted to:
* Enter input/output folders
* Choose which file types to convert (comma-separated)
* Enable/disable logging, dry run, and force conversion

💾 Config is saved between runs in `conversion_config.json`.

### 🖱️ How to Use: GUI Script

```bash
python gui/gui_converter.py
```
* Browse and select your input/output folders
* Use checkboxes to select file types
* Enable dry run, logging, and force conversion with simple toggles
* A progress bar shows conversion status

🧠 All preferences are saved automatically.

### 🔧 Requirements

* Python 3.8+
* [`markitdown`](https://github.com/microsoft/markitdown)
* Optional: `pydub` and `ffmpeg` for audio file support

## 📄 License
This project is licensed under the [MIT License](LICENSE).

## 🙋‍♂️ Author
Created by **Sascha D. Kasper** – [LeanProductivity](https://sascha-kasper.com)
Tutorial: https://youtu.be/vvZ11rPff14