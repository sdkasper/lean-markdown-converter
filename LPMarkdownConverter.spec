# -*- mode: python ; coding: utf-8 -*-

import sys
from PyInstaller.utils.hooks import collect_data_files

# Collect all Magika data (models, config, etc.)
magika_datas = collect_data_files('magika', include_py_files=False)

# Analysis: include script, data files, binaries, and runtime hooks
a = Analysis(
    ['gui/gui_converter.py'],
    pathex=['.'],
    binaries=[
        ('resources/bin/ffmpeg.exe', 'resources/bin'),
    ],
    datas=[
        ('resources', 'resources'),
        *magika_datas,
    ],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=['hide_console.py'],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
)

# Create Python archive
pyz = PYZ(
    a.pure,
    a.zipped_data,
)

# Build the executable
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='LPMarkdownConverter',
    debug=False,
    strip=False,
    upx=True,
    upx_exclude=['ffmpeg.exe'],
    console=False,
    icon='resources/LeanProductivity.ico',
)
