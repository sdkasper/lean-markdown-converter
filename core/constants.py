"""Shared constants for Lean Markdown Converter.

Single source of truth for app identity, the extension allowlist, and
category groupings consumed by both the GUI and CLI layers.
"""

APP_NAME = "Lean Markdown Converter"
VERSION = "2.0.1"
AUTHOR_NAME = "Sascha D. Kasper - LeanProductivity"
HELP_URL = "https://github.com/microsoft/markitdown"
APPDATA_VENDOR_DIR = "LeanProductivity"

# Hardcoded allowlist — never include executable/dangerous types
# (.exe, .dll, .ps1, .bat, .zip). Changes here require test updates
# (tests/core/test_extensions.py enforces the exact set).
SUPPORTED_EXTENSIONS = frozenset({
    ".csv", ".doc", ".docx", ".epub", ".htm", ".html",
    ".ipynb", ".jpeg", ".jpg", ".json", ".m4a", ".mp3", ".msg", ".pdf",
    ".png", ".ppt", ".pptx", ".wav", ".xls", ".xlsx", ".xml",
})
# Note: .bmp, .gif, .tiff are NOT included — MarkItDown's ImageConverter only
# accepts .jpg/.jpeg/.png (verified against markitdown 0.1.5 and 0.1.6). Other
# image extensions raise UnsupportedFormatException regardless of LLM config.

EXT_GROUPS = {
    "Documents":    [".doc", ".docx", ".epub", ".msg", ".pdf", ".ppt", ".pptx"],
    "Spreadsheets": [".csv", ".xls", ".xlsx"],
    "Audio":        [".m4a", ".mp3", ".wav"],
    "Images":       [".jpeg", ".jpg", ".png"],
    "Web / Data":   [".htm", ".html", ".ipynb", ".json", ".xml"],
}

AUDIO_EXTENSIONS = frozenset({".m4a", ".mp3", ".wav"})
IMAGE_EXTENSIONS = frozenset({".jpeg", ".jpg", ".png"})
