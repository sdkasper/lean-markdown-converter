"""Conversion loop: per-file conversion and the sequential batch runner.

Mirrors the conversion loop that used to live inline in worker_thread()
(gui/gui_converter.py) and the main script body of terminal/cli_converter.py:
call MarkItDown().convert(), guard against empty output, write the result,
and track counts (including audio-specific counters per NFR-006).
"""

import traceback
from dataclasses import dataclass

from core.constants import AUDIO_EXTENSIONS
from core.logging_util import RunLogger


@dataclass
class ConversionCounts:
    """Running tally for a single conversion run."""
    converted: int = 0
    overwritten: int = 0
    skipped_empty: int = 0
    failed: int = 0
    audio_attempted: int = 0
    audio_converted: int = 0
    audio_failed: int = 0
    cancelled: bool = False


def convert_one(task, md, run_logger: RunLogger) -> str:
    """Convert a single ConversionTask with the given MarkItDown instance.

    Returns one of: 'converted', 'overwritten', 'empty', 'error'.
    Never raises - all exceptions from md.convert() or the file write are
    caught, logged, and reported as 'error' so the batch loop can continue.

    NEVER log anything that could contain an API key. Exception messages
    surfaced by openai-compatible clients describe HTTP/auth failures, not
    the key itself, so str(e) here is safe.
    """
    src = task.src
    dst = task.dst
    is_audio = src.suffix.lower() in AUDIO_EXTENSIONS

    try:
        result = md.convert(str(src))
        content = result.text_content or ""

        if not content.strip():
            run_logger.log(f"Skipped (empty output): {src}")
            return "empty"

        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(content, encoding="utf-8")

        if task.existed:
            run_logger.log(f"Overwritten: {src}")
            return "overwritten"

        run_logger.log(f"Converted: {src}")
        return "converted"

    except Exception as e:
        exc_type = type(e).__name__
        err = str(e)
        if is_audio:
            # NFR-006: audio conversion failures get a truncated traceback
            # to aid FFmpeg/pydub diagnosis.
            tb = traceback.format_exc(limit=5)
            run_logger.log(f"Audio Conversion Error: {src} -> {exc_type}: {err}")
            run_logger.log(f"Traceback: {tb}")
        else:
            run_logger.log(f"Error: {src} -> {exc_type}: {err}")
        return "error"


def run_conversion(tasks, md, *, on_progress=None, should_cancel=None, run_logger: RunLogger) -> ConversionCounts:
    """Sequentially convert every task, tallying results into ConversionCounts.

    - should_cancel() is checked BEFORE each file ("finish current file"
      semantics: a file already in flight is never interrupted mid-convert).
    - on_progress(i, total, src_name) is invoked AFTER each file completes.
    - Audio-specific counters (audio_attempted/converted/failed) increment
      only for files whose suffix is in AUDIO_EXTENSIONS.
    """
    counts = ConversionCounts()
    total = len(tasks)

    for i, task in enumerate(tasks, start=1):
        if should_cancel is not None and should_cancel():
            counts.cancelled = True
            break

        is_audio = task.src.suffix.lower() in AUDIO_EXTENSIONS
        if is_audio:
            counts.audio_attempted += 1

        status = convert_one(task, md, run_logger)

        if status == "converted":
            counts.converted += 1
            if is_audio:
                counts.audio_converted += 1
        elif status == "overwritten":
            counts.overwritten += 1
            if is_audio:
                counts.audio_converted += 1
        elif status == "empty":
            counts.skipped_empty += 1
        elif status == "error":
            counts.failed += 1
            if is_audio:
                counts.audio_failed += 1

        if on_progress is not None:
            on_progress(i, total, task.src.name)

    return counts
