#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Test converter on all files in Input/ directory"""

import os
import sys
import io

# Fix encoding for Windows console
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from pathlib import Path
from markitdown import MarkItDown

# Setup paths
input_dir = Path("D:/GitProjects/lean-markdown-converter/Input")
output_dir = Path("D:/Temp/lmc")
output_dir.mkdir(parents=True, exist_ok=True)

# Initialize MarkItDown
converter = MarkItDown()

# Supported extensions (from gui_converter.py)
SUPPORTED = {
    ".bmp", ".csv", ".doc", ".docx", ".epub", ".gif", ".htm", ".html",
    ".ipynb", ".jpeg", ".jpg", ".json", ".m4a", ".mp3", ".msg", ".pdf", ".png",
    ".ppt", ".pptx", ".tiff", ".wav", ".xls", ".xlsx", ".xml"
}

# Find all files and convert
results = {"success": [], "failed": []}

for file_path in sorted(input_dir.rglob("*")):
    if not file_path.is_file():
        continue

    ext = file_path.suffix.lower()
    if ext not in SUPPORTED:
        print(f"⊘ SKIP: {file_path.relative_to(input_dir)} (unsupported: {ext})")
        continue

    try:
        # Read and convert
        result = converter.convert(str(file_path))

        # Determine output filename
        relative = file_path.relative_to(input_dir)
        output_file = output_dir / f"{relative.stem}.md"
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Write converted content
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(result.text_content)

        print(f"✅ {relative.stem:40} → {output_file.name}")
        results["success"].append(str(relative))

    except Exception as e:
        print(f"❌ {file_path.relative_to(input_dir)} : {type(e).__name__}: {str(e)[:80]}")
        results["failed"].append((str(file_path.relative_to(input_dir)), str(e)))

print(f"\n{'='*70}")
print(f"✅ Converted: {len(results['success'])} files")
print(f"❌ Failed:    {len(results['failed'])} files")
if results["failed"]:
    print(f"\nFailed files:")
    for fname, err in results["failed"]:
        print(f"  - {fname}: {err[:60]}")
