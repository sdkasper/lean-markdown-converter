"""Run logging for the conversion pipeline.

RunLogger writes a timestamped log file per run under logs_dir, created
lazily on the first log() call so a run that logs nothing (e.g. an empty
task list) never touches disk. All I/O errors are swallowed - a logging
failure must never abort a conversion run.
"""

from datetime import datetime
from pathlib import Path


class RunLogger:
    """Timestamped run logger. No-ops entirely when enabled=False."""

    def __init__(self, logs_dir: Path, version: str, enabled: bool):
        self.logs_dir = Path(logs_dir)
        self.version = version
        self.enabled = enabled
        self._log_path = None

    def log(self, line: str) -> None:
        """Append a timestamped line to the run's log file. Never raises."""
        if not self.enabled:
            return

        now = datetime.now()
        formatted = f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] {line}"

        try:
            if self._log_path is None:
                self.logs_dir.mkdir(parents=True, exist_ok=True)
                stamp = now.strftime("%Y%m%d_%H%M%S")
                candidate = self.logs_dir / f"conversion_{stamp}.log"
                header = f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Lean Markdown Converter v{self.version}\n"
                candidate.write_text(header, encoding="utf-8")
                self._log_path = candidate

            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(formatted + "\n")
        except OSError:
            pass

    def finalize(self, summary: str) -> Path:
        """Write the summary as a final log line. Returns the log path if a
        file was written this run, else None. No-op (returns None) when
        disabled.
        """
        if not self.enabled:
            return None
        self.log(summary)
        return self._log_path


def format_summary(counts) -> str:
    """Human-readable multi-line summary of a ConversionCounts instance."""
    lines = [
        "=== Conversion Summary ===",
        f"Converted: {counts.converted}",
        f"Overwritten: {counts.overwritten}",
        f"Skipped (empty output): {counts.skipped_empty}",
        f"Failed: {counts.failed}",
        f"Audio attempted: {counts.audio_attempted}",
        f"Audio converted: {counts.audio_converted}",
        f"Audio failed: {counts.audio_failed}",
        f"Cancelled: {counts.cancelled}",
    ]
    return "\n".join(lines)
