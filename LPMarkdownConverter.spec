# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Lean Markdown Converter v2.0.0
#
# Key decisions (see plan / CLAUDE.md):
# - Entry point is the thin gui/main.py wrapper, not the app module.
# - NO external binaries embedded: ffmpeg/ffprobe/exiftool ship as optional
#   Inno Setup components installed to {app}\tools\ and are discovered at
#   runtime by core/binaries.py. This keeps the exe small (~60-90 MB) and
#   onefile startup fast (NFR-004: <= 5s).
# - UPX is DISABLED: compressing native extension modules (_pydantic_core,
#   jiter, onnxruntime) is the prime suspect for the v1.1.0 frozen-build
#   "TypeError: function() argument 'code' must be code, not str" that
#   blocked five consecutive builds. Do not re-enable without an explicit
#   exclusion list and repeated clean-machine OCR-init verification.
# - collect_submodules for openai/httpx/pydantic/markitdown: these SDKs use
#   lazy imports that PyInstaller's static analysis misses in onefile mode.

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Magika model + config data (file type detection used by markitdown)
magika_datas = collect_data_files('magika', include_py_files=False)
# CA bundle for TLS verification (httpx/openai outbound calls)
certifi_datas = collect_data_files('certifi')

hiddenimports = [
    *collect_submodules('openai'),
    *collect_submodules('httpx'),
    *collect_submodules('httpcore'),
    *collect_submodules('anyio'),
    *collect_submodules('pydantic'),
    *collect_submodules('markitdown'),
    'pydantic_core._pydantic_core',
    'jiter.jiter',
    'distro',
    'sniffio',
    'certifi',
    'h11',
    'idna',
    'charset_normalizer',
]

a = Analysis(
    ['gui/main.py'],
    pathex=['.'],
    binaries=[],  # ffmpeg/ffprobe/exiftool are installer components, never embedded
    datas=[
        ('resources/LeanProductivity.ico', 'resources'),
        *magika_datas,
        *certifi_datas,
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=['hide_console.py'],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
)

pyz = PYZ(
    a.pure,
    a.zipped_data,
)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='LPMarkdownConverter',
    debug=False,
    strip=False,
    upx=False,  # deliberately off - see header comment
    console=False,
    icon='resources/LeanProductivity.ico',
)
