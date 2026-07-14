"""File discovery and output-path mirroring for the conversion pipeline.

Walks the input directory, filters by the supported-extension allowlist,
mirrors the directory structure under the output directory (changing the
suffix to .md), and applies up-to-date / force skip logic plus path-safety
checks on both the source and destination side. Mirrors the collection
loop that used to live inline in terminal/cli_converter.py and
gui/gui_converter.py (NFR-001: path traversal prevention via
core.paths.is_safe_path).
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from core.constants import SUPPORTED_EXTENSIONS
from core.paths import is_safe_path


@dataclass(frozen=True)
class ConversionTask:
    """A single file scheduled for conversion.

    src      - absolute source file path
    dst      - mirrored destination path under the output dir, suffix .md
    existed  - True if dst already existed before this run (used to
               distinguish "converted" from "overwritten" counts)
    """
    src: Path
    dst: Path
    existed: bool


@dataclass(frozen=True)
class ScanResult:
    """Result of a full directory scan."""
    tasks: list = field(default_factory=list)
    skipped_up_to_date: int = 0
    skipped_unsafe: int = 0


def collect_files(input_dir: Path, output_dir: Path, extensions: set, force: bool = False) -> ScanResult:
    """Recursively walk input_dir and build the list of conversion tasks.

    - Filters to extensions ∩ SUPPORTED_EXTENSIONS, case-insensitively.
    - Mirrors input/a/b/f.pdf -> output/a/b/f.md.
    - Applies is_safe_path against input_dir (source) and output_dir
      (destination) independently; unsafe entries are counted and skipped,
      never raised.
    - Skips files whose destination already exists and is at least as new
      as the source, unless force=True.
    - Never raises on unreadable/vanishing entries - they are skipped.
    - Deterministic ordering (sorted by source path).
    """
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    allowed = {str(e).lower() for e in extensions} & SUPPORTED_EXTENSIONS

    candidates = []
    for root, _, files in os.walk(input_dir):
        for name in files:
            src = Path(root) / name
            if src.suffix.lower() not in allowed:
                continue
            candidates.append(src)

    tasks = []
    skipped_up_to_date = 0
    skipped_unsafe = 0

    for src in sorted(candidates):
        if not is_safe_path(input_dir, src):
            skipped_unsafe += 1
            continue

        try:
            rel = src.relative_to(input_dir)
        except ValueError:
            skipped_unsafe += 1
            continue

        dst = output_dir / rel.with_suffix(".md")

        if not is_safe_path(output_dir, dst):
            skipped_unsafe += 1
            continue

        try:
            existed = dst.exists()
        except OSError:
            existed = False

        if existed and not force:
            try:
                if dst.stat().st_mtime >= src.stat().st_mtime:
                    skipped_up_to_date += 1
                    continue
            except OSError:
                pass

        tasks.append(ConversionTask(src=src, dst=dst, existed=existed))

    return ScanResult(tasks=tasks, skipped_up_to_date=skipped_up_to_date, skipped_unsafe=skipped_unsafe)


def count_files(input_dir: Path, extensions: set) -> int:
    """Cheap preview count for the GUI's live scan label.

    Walk + extension filter only - no mtime comparison, no path-safety
    check, no dataclass construction. Never raises: returns 0 for a
    nonexistent/unreadable input_dir.
    """
    input_dir = Path(input_dir)
    allowed = {str(e).lower() for e in extensions} & SUPPORTED_EXTENSIONS

    try:
        count = 0
        for _, _, files in os.walk(input_dir):
            for name in files:
                if Path(name).suffix.lower() in allowed:
                    count += 1
        return count
    except OSError:
        return 0
