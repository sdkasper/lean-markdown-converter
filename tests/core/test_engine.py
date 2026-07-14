"""Tests for core.engine (TC-001): convert_one, run_conversion, and the
RunLogger/format_summary collaboration.

Uses the fake_md / make_task fixtures from tests/core/conftest.py for pure
unit tests, plus a handful of @pytest.mark.integration tests that drive the
full pipeline with a real MarkItDown instance against tests/fixtures/.
"""

from pathlib import Path

import pytest
from markitdown import MarkItDown

from core.engine import ConversionCounts, convert_one, run_conversion
from core.logging_util import RunLogger, format_summary
from core.scanner import ConversionTask, collect_files


# ═══════════════════════════════════════════════════════════════════════════════
# convert_one - status outcomes
# ═══════════════════════════════════════════════════════════════════════════════

class TestConvertOne:
    def test_converted_writes_file(self, make_task, fake_md):
        task = make_task(name="a.csv", content="x", existed=False)
        md = fake_md(default_text="# hello")
        logger = RunLogger(task.dst.parent / "logs", "2.0.0", enabled=False)

        status = convert_one(task, md, logger)

        assert status == "converted"
        assert task.dst.is_file()
        assert task.dst.read_text(encoding="utf-8") == "# hello"

    def test_empty_text_returns_empty_and_writes_nothing(self, make_task, fake_md, tmp_path):
        task = make_task(name="a.csv", content="x", existed=False)
        md = fake_md(default_text="   ")
        logs_dir = tmp_path / "logs"
        logger = RunLogger(logs_dir, "2.0.0", enabled=True)

        status = convert_one(task, md, logger)

        assert status == "empty"
        assert not task.dst.exists()
        log_text = logger._log_path.read_text(encoding="utf-8")
        assert "Skipped (empty output)" in log_text

    def test_convert_raising_returns_error(self, make_task, fake_md, tmp_path):
        task = make_task(name="a.csv", content="x", existed=False)
        md = fake_md(raises={str(task.src): ValueError("bad file")})
        logger = RunLogger(tmp_path / "logs", "2.0.0", enabled=True)

        status = convert_one(task, md, logger)

        assert status == "error"
        assert not task.dst.exists()
        log_text = logger._log_path.read_text(encoding="utf-8")
        assert "ValueError" in log_text
        assert "bad file" in log_text

    def test_overwritten_when_task_existed(self, make_task, fake_md):
        task = make_task(name="a.csv", content="x", existed=True)
        md = fake_md(default_text="new content")
        logger = RunLogger(task.dst.parent / "logs", "2.0.0", enabled=False)

        status = convert_one(task, md, logger)

        assert status == "overwritten"
        assert task.dst.read_text(encoding="utf-8") == "new content"

    def test_audio_error_logs_traceback(self, make_task, fake_md, tmp_path):
        task = make_task(name="clip.mp3", content="x", existed=False)
        md = fake_md(raises={str(task.src): RuntimeError("ffmpeg missing")})
        logger = RunLogger(tmp_path / "logs", "2.0.0", enabled=True)

        status = convert_one(task, md, logger)

        assert status == "error"
        log_text = logger._log_path.read_text(encoding="utf-8")
        assert "Audio Conversion Error" in log_text
        assert "Traceback" in log_text


# ═══════════════════════════════════════════════════════════════════════════════
# run_conversion - loop semantics
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunConversion:
    def test_loop_continues_after_error(self, make_task, fake_md, tmp_path):
        good = make_task(name="good.csv", content="x")
        bad = make_task(name="bad.pdf", content="y")
        md = fake_md(raises={str(bad.src): OSError("boom")}, default_text="ok")
        logger = RunLogger(tmp_path / "logs", "2.0.0", enabled=False)

        counts = run_conversion([good, bad], md, run_logger=logger)

        assert counts.converted == 1
        assert counts.failed == 1

    def test_overwritten_counted_separately_from_converted(self, make_task, fake_md, tmp_path):
        new_task = make_task(name="new.csv", content="x", existed=False)
        old_task = make_task(name="old.csv", content="y", existed=True)
        md = fake_md(default_text="content")
        logger = RunLogger(tmp_path / "logs", "2.0.0", enabled=False)

        counts = run_conversion([new_task, old_task], md, run_logger=logger)

        assert counts.converted == 1
        assert counts.overwritten == 1

    def test_cancel_after_n_files_stops_remaining(self, make_task, fake_md, tmp_path):
        tasks = [make_task(name=f"f{i}.csv", content="x") for i in range(5)]
        md = fake_md(default_text="ok")
        logger = RunLogger(tmp_path / "logs", "2.0.0", enabled=False)

        processed = []

        def should_cancel():
            return len(processed) >= 2

        def on_progress(i, total, name):
            processed.append(name)

        counts = run_conversion(
            tasks, md, on_progress=on_progress, should_cancel=should_cancel, run_logger=logger
        )

        assert counts.cancelled is True
        assert len(processed) == 2
        assert counts.converted == 2

    def test_on_progress_called_with_sequential_i_total_name(self, make_task, fake_md, tmp_path):
        tasks = [make_task(name=f"f{i}.csv", content="x") for i in range(3)]
        md = fake_md(default_text="ok")
        logger = RunLogger(tmp_path / "logs", "2.0.0", enabled=False)
        calls = []

        def on_progress(i, total, name):
            calls.append((i, total, name))

        run_conversion(tasks, md, on_progress=on_progress, run_logger=logger)

        assert calls == [
            (1, 3, "f0.csv"),
            (2, 3, "f1.csv"),
            (3, 3, "f2.csv"),
        ]

    def test_audio_counters_increment_only_for_audio_extensions(self, make_task, fake_md, tmp_path):
        audio_task = make_task(name="clip.mp3", content="x")
        doc_task = make_task(name="doc.csv", content="y")
        md = fake_md(default_text="ok")
        logger = RunLogger(tmp_path / "logs", "2.0.0", enabled=False)

        counts = run_conversion([audio_task, doc_task], md, run_logger=logger)

        assert counts.audio_attempted == 1
        assert counts.audio_converted == 1
        assert counts.converted == 2  # both files still count toward overall converted

    def test_audio_failed_counter_increments_on_error(self, make_task, fake_md, tmp_path):
        audio_task = make_task(name="clip.wav", content="x")
        md = fake_md(raises={str(audio_task.src): RuntimeError("no ffmpeg")})
        logger = RunLogger(tmp_path / "logs", "2.0.0", enabled=False)

        counts = run_conversion([audio_task], md, run_logger=logger)

        assert counts.audio_attempted == 1
        assert counts.audio_failed == 1
        assert counts.failed == 1


# ═══════════════════════════════════════════════════════════════════════════════
# RunLogger
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunLogger:
    def test_disabled_logger_never_creates_file_and_finalize_returns_none(self, tmp_path):
        logs_dir = tmp_path / "logs"
        logger = RunLogger(logs_dir, "2.0.0", enabled=False)

        logger.log("something happened")
        result = logger.finalize("done")

        assert result is None
        assert not logs_dir.exists() or list(logs_dir.iterdir()) == []

    def test_enabled_logger_creates_file_containing_summary(self, tmp_path):
        logs_dir = tmp_path / "logs"
        logger = RunLogger(logs_dir, "2.0.0", enabled=True)

        logger.log("first event")
        log_path = logger.finalize("=== Conversion Summary ===\nConverted: 1")

        assert log_path is not None
        assert log_path.is_file()
        content = log_path.read_text(encoding="utf-8")
        assert "first event" in content
        assert "Conversion Summary" in content

    def test_log_is_noop_before_any_call_creates_no_file(self, tmp_path):
        logs_dir = tmp_path / "logs"
        RunLogger(logs_dir, "2.0.0", enabled=True)
        assert not logs_dir.exists()

    def test_log_never_raises_on_unwritable_dir(self, tmp_path):
        # Point logs_dir at a path that collides with an existing file,
        # making mkdir() fail - log() must swallow this, not raise.
        blocker = tmp_path / "blocker"
        blocker.write_text("x", encoding="utf-8")
        logger = RunLogger(blocker / "logs", "2.0.0", enabled=True)

        logger.log("this must not raise")  # no exception expected


# ═══════════════════════════════════════════════════════════════════════════════
# format_summary
# ═══════════════════════════════════════════════════════════════════════════════

class TestFormatSummary:
    def test_contains_all_count_fields(self):
        counts = ConversionCounts(
            converted=1, overwritten=2, skipped_empty=3, failed=4,
            audio_attempted=5, audio_converted=6, audio_failed=7, cancelled=True,
        )
        summary = format_summary(counts)

        assert "1" in summary
        assert "Converted" in summary
        assert "2" in summary
        assert "Overwritten" in summary
        assert "3" in summary
        assert "Failed: 4" in summary
        assert "5" in summary
        assert "6" in summary
        assert "7" in summary
        assert "True" in summary


# ═══════════════════════════════════════════════════════════════════════════════
# Real MarkItDown integration
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.integration
class TestRealMarkItDownIntegration:
    """Drive run_conversion end-to-end with a real MarkItDown instance."""

    def test_csv_html_json_produce_nonempty_md(self, temp_input_dir, temp_output_dir):
        result = collect_files(
            temp_input_dir, temp_output_dir, {".csv", ".html", ".json"}, force=True
        )
        assert result.tasks, "Expected at least one collected task from temp_input_dir"

        md = MarkItDown()
        logger = RunLogger(temp_output_dir / "logs", "2.0.0", enabled=False)
        counts = run_conversion(result.tasks, md, run_logger=logger)

        assert counts.failed == 0
        assert counts.converted + counts.overwritten == len(result.tasks)
        for task in result.tasks:
            assert task.dst.is_file()
            assert len(task.dst.read_text(encoding="utf-8").strip()) > 0

    def test_real_fixture_csv_converts(self, fixture_csv, tmp_path):
        task = ConversionTask(src=fixture_csv, dst=tmp_path / "out.md", existed=False)
        md = MarkItDown()
        logger = RunLogger(tmp_path / "logs", "2.0.0", enabled=False)

        status = convert_one(task, md, logger)

        assert status == "converted"
        assert task.dst.is_file()
        assert len(task.dst.read_text(encoding="utf-8").strip()) > 0

    def test_real_fixture_html_converts(self, fixture_html, tmp_path):
        task = ConversionTask(src=fixture_html, dst=tmp_path / "out.md", existed=False)
        md = MarkItDown()
        logger = RunLogger(tmp_path / "logs", "2.0.0", enabled=False)

        status = convert_one(task, md, logger)

        assert status == "converted"
        assert "Hello World" in task.dst.read_text(encoding="utf-8")
