# hide_console.py - PyInstaller runtime hook
#
# Suppresses console window flashes when the windowed exe spawns
# subprocesses (ffmpeg/ffprobe/exiftool).
#
# MUST be a subclass, not a wrapper function: asyncio.windows_utils does
# `class Popen(subprocess.Popen)` at import time, and subclassing a plain
# function raises "TypeError: function() argument 'code' must be code,
# not str". That single line was the root cause of the v1.1.0 frozen-build
# LLM failure (openai imports asyncio; nothing else in the app does).
import subprocess


class _NoWindowPopen(subprocess.Popen):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('creationflags', subprocess.CREATE_NO_WINDOW)
        super().__init__(*args, **kwargs)


subprocess.Popen = _NoWindowPopen
