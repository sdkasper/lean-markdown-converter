"""Tests for core.scanner.collect_files / count_files (TC-006).

Ported from the old tests/test_file_collection.py, which replicated the
inline os.walk loop from terminal/cli_converter.py. Here we exercise the
real core.scanner implementation directly.
"""

import os
from pathlib import Path

import pytest

from core.scanner import ConversionTask, ScanResult, collect_files, count_files

CSV = {".csv"}


# ═══════════════════════════════════════════════════════════════════════════════
# Basic discovery
# ═══════════════════════════════════════════════════════════════════════════════

class TestBasicDiscovery:
    def test_flat_walk_collects_all_supported(self, tmp_path):
        """A flat directory with one file per supported extension is fully collected."""
        inp = tmp_path / "input"
        out = tmp_path / "output"
        inp.mkdir(); out.mkdir()
        (inp / "a.csv").write_text("a,b\n", encoding="utf-8")
        (inp / "b.html").write_text("<html/>", encoding="utf-8")
        (inp / "c.json").write_text("{}", encoding="utf-8")

        result = collect_files(inp, out, {".csv", ".html", ".json"})
        assert isinstance(result, ScanResult)
        assert len(result.tasks) == 3
        assert all(isinstance(t, ConversionTask) for t in result.tasks)

    def test_nested_mirroring(self, tmp_path):
        """input/a/b/f.pdf -> output/a/b/f.md."""
        inp = tmp_path / "input"
        out = tmp_path / "output"
        sub = inp / "a" / "b"
        sub.mkdir(parents=True); out.mkdir()
        (sub / "f.pdf").write_bytes(b"%PDF-1.4 fake")

        result = collect_files(inp, out, {".pdf"})
        assert len(result.tasks) == 1
        task = result.tasks[0]
        assert task.src == sub / "f.pdf"
        assert task.dst == out / "a" / "b" / "f.md"

    def test_empty_folder_yields_empty_result(self, tmp_path):
        inp = tmp_path / "input"
        out = tmp_path / "output"
        inp.mkdir(); out.mkdir()

        result = collect_files(inp, out, CSV)
        assert result.tasks == []
        assert result.skipped_up_to_date == 0
        assert result.skipped_unsafe == 0

    def test_only_unsupported_extensions_yields_empty(self, tmp_path):
        """.txt and .log files are never in SUPPORTED_EXTENSIONS."""
        inp = tmp_path / "input"
        out = tmp_path / "output"
        inp.mkdir(); out.mkdir()
        (inp / "notes.txt").write_text("hi", encoding="utf-8")
        (inp / "run.log").write_text("log", encoding="utf-8")

        result = collect_files(inp, out, {".txt", ".log"})
        assert result.tasks == []


# ═══════════════════════════════════════════════════════════════════════════════
# Up-to-date skip logic
# ═══════════════════════════════════════════════════════════════════════════════

class TestSkipLogic:
    def test_dst_newer_is_skipped(self, tmp_path):
        inp = tmp_path / "input"; out = tmp_path / "output"
        inp.mkdir(); out.mkdir()
        src = inp / "doc.csv"
        src.write_text("a,b\n", encoding="utf-8")
        dst = out / "doc.md"
        dst.write_text("# already done", encoding="utf-8")
        future = src.stat().st_mtime + 10
        os.utime(dst, (future, future))

        result = collect_files(inp, out, CSV, force=False)
        assert result.tasks == []
        assert result.skipped_up_to_date == 1

    def test_src_newer_is_included(self, tmp_path):
        inp = tmp_path / "input"; out = tmp_path / "output"
        inp.mkdir(); out.mkdir()
        dst = out / "doc.md"
        dst.write_text("# old output", encoding="utf-8")
        src = inp / "doc.csv"
        src.write_text("a,b\n", encoding="utf-8")
        future = dst.stat().st_mtime + 10
        os.utime(src, (future, future))

        result = collect_files(inp, out, CSV, force=False)
        assert len(result.tasks) == 1
        assert result.skipped_up_to_date == 0
        assert result.tasks[0].existed is True

    def test_force_includes_all(self, tmp_path):
        inp = tmp_path / "input"; out = tmp_path / "output"
        inp.mkdir(); out.mkdir()
        src = inp / "doc.csv"
        src.write_text("a,b\n", encoding="utf-8")
        dst = out / "doc.md"
        dst.write_text("# old", encoding="utf-8")
        future = src.stat().st_mtime + 100
        os.utime(dst, (future, future))

        result = collect_files(inp, out, CSV, force=True)
        assert len(result.tasks) == 1
        assert result.skipped_up_to_date == 0

    def test_existed_flag_false_when_no_prior_output(self, tmp_path):
        inp = tmp_path / "input"; out = tmp_path / "output"
        inp.mkdir(); out.mkdir()
        (inp / "new.csv").write_text("a\n", encoding="utf-8")

        result = collect_files(inp, out, CSV, force=False)
        assert len(result.tasks) == 1
        assert result.tasks[0].existed is False

    def test_existed_flag_true_when_forced_over_existing(self, tmp_path):
        inp = tmp_path / "input"; out = tmp_path / "output"
        inp.mkdir(); out.mkdir()
        src = inp / "doc.csv"
        src.write_text("a,b\n", encoding="utf-8")
        dst = out / "doc.md"
        dst.write_text("# old", encoding="utf-8")
        future = src.stat().st_mtime + 100
        os.utime(dst, (future, future))

        result = collect_files(inp, out, CSV, force=True)
        assert result.tasks[0].existed is True


# ═══════════════════════════════════════════════════════════════════════════════
# Extension intersection with SUPPORTED_EXTENSIONS
# ═══════════════════════════════════════════════════════════════════════════════

class TestExtensionIntersection:
    def test_extension_not_in_supported_set_yields_nothing(self, tmp_path):
        """Passing {'.exe'} must never collect anything, even if a file
        with that suffix exists - .exe is not in SUPPORTED_EXTENSIONS."""
        inp = tmp_path / "input"; out = tmp_path / "output"
        inp.mkdir(); out.mkdir()
        (inp / "tool.exe").write_bytes(b"MZ")

        result = collect_files(inp, out, {".exe"})
        assert result.tasks == []

    def test_case_insensitive_suffix_match(self, tmp_path):
        """A .PDF file matches the .pdf entry in SUPPORTED_EXTENSIONS."""
        inp = tmp_path / "input"; out = tmp_path / "output"
        inp.mkdir(); out.mkdir()
        (inp / "report.PDF").write_bytes(b"%PDF-1.4")

        result = collect_files(inp, out, {".pdf"})
        assert len(result.tasks) == 1
        assert result.tasks[0].dst.name == "report.md"


# ═══════════════════════════════════════════════════════════════════════════════
# count_files
# ═══════════════════════════════════════════════════════════════════════════════

class TestCountFiles:
    def test_count_matches_collect_on_same_tree(self, tmp_path):
        inp = tmp_path / "input"; out = tmp_path / "output"
        inp.mkdir(); out.mkdir()
        (inp / "a.csv").write_text("a\n", encoding="utf-8")
        (inp / "b.csv").write_text("b\n", encoding="utf-8")
        sub = inp / "nested"; sub.mkdir()
        (sub / "c.csv").write_text("c\n", encoding="utf-8")
        (inp / "d.txt").write_text("ignored", encoding="utf-8")

        result = collect_files(inp, out, CSV)
        assert count_files(inp, CSV) == len(result.tasks)

    def test_count_files_returns_zero_for_nonexistent_dir(self, tmp_path):
        missing = tmp_path / "does_not_exist"
        assert count_files(missing, CSV) == 0
