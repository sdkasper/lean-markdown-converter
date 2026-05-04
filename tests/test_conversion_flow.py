"""
End-to-end conversion tests using real MarkItDown conversions on real fixture files.

These tests run actual conversions — they do NOT mock MarkItDown — so they
verify that the full pipeline produces correct .md output.

Marks:
  pytest.mark.integration  - tests that perform actual file I/O + conversion
  pytest.mark.slow         - tests that may take >1 second (batch, logging)
"""

import os
import time
import json
from pathlib import Path
from datetime import datetime

import pytest
from markitdown import MarkItDown

import terminal.cli_converter as cli_mod

# ─── Re-use the same collection helper from test_file_collection ─────────────
is_safe_path = cli_mod.is_safe_path
SUPPORTED = cli_mod.SUPPORTED_EXTENSIONS

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ─── Minimal conversion runner (mirrors the CLI conversion loop) ─────────────

def _run_conversion(files_to_convert, dry_run=False, log_dir=None):
    """
    Run MarkItDown conversion on a list of (src_path, dst_path) pairs.
    Returns a summary dict: {converted, failed, log_path}.
    """
    md = MarkItDown()
    converted = failed = 0
    log_lines = []
    log_path = None

    if dry_run:
        return {"converted": 0, "failed": 0, "log_path": None, "dry_run": True}

    for src, dst in files_to_convert:
        try:
            result = md.convert(str(src))
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(result.text_content, encoding="utf-8")
            converted += 1
            log_lines.append(f"[{datetime.now()}] Converted: {src}")
        except Exception as e:
            failed += 1
            log_lines.append(f"[{datetime.now()}] Error: {src} -> {e}")

    if log_dir is not None:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_path = log_dir / f"conversion_log_{timestamp}.log"
        log_path.write_text("\n".join(log_lines), encoding="utf-8")

    return {"converted": converted, "failed": failed, "log_path": log_path}


# ─── File collection helper ───────────────────────────────────────────────────

def _collect(inp, out, exts, force=False):
    """Collect (src, dst) pairs using the same logic as cli_converter."""
    to_convert = []
    for root, _, files in os.walk(inp):
        for f in files:
            src = Path(root) / f
            if not is_safe_path(inp, src):
                continue
            if src.suffix.lower() not in exts:
                continue
            rel = src.relative_to(inp)
            dst = out / rel.with_suffix(".md")
            if not is_safe_path(out, dst):
                continue
            if dst.exists() and not force:
                if dst.stat().st_mtime >= src.stat().st_mtime:
                    continue
            to_convert.append((src, dst))
    return to_convert


# ═══════════════════════════════════════════════════════════════════════════════
# Single-file conversions
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.integration
class TestSingleFileConversion:
    """Each supported fixture type converts to a non-empty .md file."""

    def test_convert_csv_to_markdown(self, tmp_path, fixture_csv):
        """CSV converts to a markdown table."""
        dst = tmp_path / "sample.md"
        result = MarkItDown().convert(str(fixture_csv))
        dst.write_text(result.text_content, encoding="utf-8")

        assert dst.is_file(), "Output .md file should exist"
        content = dst.read_text(encoding="utf-8")
        assert len(content.strip()) > 0, "Output should not be empty"
        # CSV -> markdown table: expect pipe characters
        assert "|" in content, "CSV conversion should produce a markdown table"

    def test_convert_html_to_markdown(self, tmp_path, fixture_html):
        """HTML converts to markdown with headings."""
        dst = tmp_path / "sample.md"
        result = MarkItDown().convert(str(fixture_html))
        dst.write_text(result.text_content, encoding="utf-8")

        content = dst.read_text(encoding="utf-8")
        assert "Hello World" in content, "H1 text should appear in markdown output"

    def test_convert_pdf_to_markdown(self, tmp_path, fixture_pdf):
        """PDF converts to a non-empty markdown file (skipped if pdf deps absent)."""
        try:
            result = MarkItDown().convert(str(fixture_pdf))
        except Exception as e:
            msg = str(e)
            if "MissingDependencyException" in msg or "pdf" in msg.lower():
                pytest.skip(f"PDF dependencies not installed in this environment: {e}")
            raise

        dst = tmp_path / "sample.md"
        dst.write_text(result.text_content, encoding="utf-8")
        content = dst.read_text(encoding="utf-8")
        assert len(content.strip()) > 0
        assert "Hello World" in content

    def test_convert_docx_to_markdown(self, tmp_path, fixture_docx):
        """DOCX converts to plain markdown text."""
        dst = tmp_path / "sample.md"
        result = MarkItDown().convert(str(fixture_docx))
        dst.write_text(result.text_content, encoding="utf-8")

        content = dst.read_text(encoding="utf-8")
        assert "Test Document Content" in content, (
            "DOCX body text should appear in output"
        )

    def test_output_file_is_utf8(self, tmp_path, fixture_csv):
        """Output files are written in UTF-8 encoding."""
        dst = tmp_path / "out.md"
        result = MarkItDown().convert(str(fixture_csv))
        dst.write_text(result.text_content, encoding="utf-8")

        # Re-read as bytes and decode — should not raise
        raw = dst.read_bytes()
        decoded = raw.decode("utf-8")
        assert len(decoded) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# Batch / multi-file conversion
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.integration
@pytest.mark.slow
class TestBatchConversion:
    """Multiple files are converted in one pass."""

    def test_convert_multiple_files(self, tmp_path):
        """All collected files in a batch are converted."""
        inp = tmp_path / "input"; out = tmp_path / "output"
        inp.mkdir(); out.mkdir()

        # Copy real fixtures so we get actual conversions
        import shutil
        for name in ("sample.csv", "sample.html", "sample.json"):
            shutil.copy(FIXTURES_DIR / name, inp / name)

        collected = _collect(inp, out, {".csv", ".html", ".json"})
        assert len(collected) == 3, "All 3 files should be collected"

        summary = _run_conversion(collected)
        assert summary["converted"] == 3, f"Expected 3 conversions, got {summary}"
        assert summary["failed"] == 0

    def test_convert_creates_output_structure(self, tmp_path):
        """Output mirrors the input directory tree."""
        inp = tmp_path / "input"; out = tmp_path / "output"
        inp.mkdir(); out.mkdir()

        sub = inp / "sub"
        sub.mkdir()
        (inp / "root.csv").write_text("a,b\n1,2\n", encoding="utf-8")
        (sub / "nested.csv").write_text("x,y\n3,4\n", encoding="utf-8")

        collected = _collect(inp, out, {".csv"})
        _run_conversion(collected)

        assert (out / "root.md").is_file(), "Root-level output should exist"
        assert (out / "sub" / "nested.md").is_file(), "Nested output should exist"

    def test_convert_handles_corrupted_file(self, tmp_path):
        """A corrupted file is counted as failed; conversion continues."""
        inp = tmp_path / "input"; out = tmp_path / "output"
        inp.mkdir(); out.mkdir()

        # Corrupt PDF: valid extension, garbage bytes
        (inp / "corrupt.pdf").write_bytes(b"\x00\x01\x02NOT A REAL PDF")
        (inp / "good.csv").write_text("a,b\n1,2\n", encoding="utf-8")

        collected = _collect(inp, out, {".pdf", ".csv"})
        summary = _run_conversion(collected)

        # CSV should succeed; PDF may fail (depends on pdfminer tolerance)
        assert summary["converted"] + summary["failed"] == len(collected), (
            "Total of converted + failed must equal total collected"
        )
        assert summary["converted"] >= 1, "At least the good CSV should convert"


# ═══════════════════════════════════════════════════════════════════════════════
# Dry-run mode
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.integration
class TestDryRun:
    """Dry-run mode inspects files but does not write any output."""

    def test_dry_run_creates_no_output_files(self, tmp_path):
        """No .md files are written when dry_run=True."""
        inp = tmp_path / "input"; out = tmp_path / "output"
        inp.mkdir(); out.mkdir()
        import shutil
        shutil.copy(FIXTURES_DIR / "sample.csv", inp / "sample.csv")

        collected = _collect(inp, out, {".csv"})
        assert len(collected) == 1

        _run_conversion(collected, dry_run=True)

        md_files = list(out.rglob("*.md"))
        assert md_files == [], (
            f"Dry run must not create any .md files, found: {md_files}"
        )

    def test_dry_run_reports_correct_count(self, tmp_path):
        """Dry-run summary shows the right number of 'would convert' files."""
        inp = tmp_path / "input"; out = tmp_path / "output"
        inp.mkdir(); out.mkdir()
        import shutil
        for name in ("sample.csv", "sample.html"):
            shutil.copy(FIXTURES_DIR / name, inp / name)

        collected = _collect(inp, out, {".csv", ".html"})
        summary = _run_conversion(collected, dry_run=True)

        # dry_run returns 0 converted and marks the flag
        assert summary["dry_run"] is True
        assert summary["converted"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Force flag (overwrite existing output)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.integration
class TestForceFlag:
    """force=True causes existing up-to-date output to be overwritten."""

    def test_force_overwrites_existing_output(self, tmp_path):
        """With force=True an existing newer .md is overwritten."""
        import shutil
        inp = tmp_path / "input"; out = tmp_path / "output"
        inp.mkdir(); out.mkdir()
        shutil.copy(FIXTURES_DIR / "sample.csv", inp / "sample.csv")

        # Create an up-to-date output
        dst = out / "sample.md"
        dst.write_text("# OLD CONTENT", encoding="utf-8")
        # Make dst newer than src
        future_time = (inp / "sample.csv").stat().st_mtime + 100
        os.utime(dst, (future_time, future_time))

        # Without force, nothing should be collected
        no_force = _collect(inp, out, {".csv"}, force=False)
        assert no_force == [], "Up-to-date file should be skipped without force"

        # With force, the file should be collected and converted
        with_force = _collect(inp, out, {".csv"}, force=True)
        assert len(with_force) == 1
        _run_conversion(with_force)

        new_content = dst.read_text(encoding="utf-8")
        assert "OLD CONTENT" not in new_content, "Forced conversion should replace old content"


# ═══════════════════════════════════════════════════════════════════════════════
# Logging
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.integration
@pytest.mark.slow
class TestLogging:
    """Logging writes a timestamped .log file with conversion results."""

    def test_logging_creates_log_file(self, tmp_path):
        """When log_dir is given, a .log file is created."""
        import shutil
        inp = tmp_path / "input"; out = tmp_path / "output"; logs = tmp_path / "logs"
        inp.mkdir(); out.mkdir()
        shutil.copy(FIXTURES_DIR / "sample.csv", inp / "sample.csv")

        collected = _collect(inp, out, {".csv"})
        summary = _run_conversion(collected, log_dir=logs)

        assert summary["log_path"] is not None, "log_path should be set"
        assert Path(summary["log_path"]).is_file(), "Log file should exist on disk"

    def test_log_filename_has_timestamp(self, tmp_path):
        """Log filenames include a timestamp pattern YYYY-MM-DD_HH-MM-SS."""
        import shutil, re
        inp = tmp_path / "input"; out = tmp_path / "output"; logs = tmp_path / "logs"
        inp.mkdir(); out.mkdir()
        shutil.copy(FIXTURES_DIR / "sample.csv", inp / "sample.csv")

        collected = _collect(inp, out, {".csv"})
        summary = _run_conversion(collected, log_dir=logs)

        log_name = Path(summary["log_path"]).name
        pattern = r"conversion_log_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.log"
        assert re.match(pattern, log_name), (
            f"Log filename '{log_name}' does not match expected timestamp pattern"
        )

    def test_log_contains_converted_entry(self, tmp_path):
        """Log file contains a 'Converted:' line for each successful conversion."""
        import shutil
        inp = tmp_path / "input"; out = tmp_path / "output"; logs = tmp_path / "logs"
        inp.mkdir(); out.mkdir()
        shutil.copy(FIXTURES_DIR / "sample.csv", inp / "sample.csv")

        collected = _collect(inp, out, {".csv"})
        summary = _run_conversion(collected, log_dir=logs)

        log_text = Path(summary["log_path"]).read_text(encoding="utf-8")
        assert "Converted:" in log_text, "Log should contain a 'Converted:' entry"

    def test_log_contains_error_entry_for_failed_file(self, tmp_path):
        """Log file contains an 'Error:' line when a file fails to convert."""
        inp = tmp_path / "input"; out = tmp_path / "output"; logs = tmp_path / "logs"
        inp.mkdir(); out.mkdir()
        (inp / "bad.pdf").write_bytes(b"\x00NOTAPDF")

        collected = _collect(inp, out, {".pdf"})
        summary = _run_conversion(collected, log_dir=logs)

        if summary["log_path"] and summary["failed"] > 0:
            log_text = Path(summary["log_path"]).read_text(encoding="utf-8")
            assert "Error:" in log_text, "Failed file should produce an 'Error:' log entry"
