"""
Tests for file discovery, skip-logic, and output path building.

The collection loop in both converters follows this pattern:
  os.walk(input_folder) -> filter by extension -> check is_safe_path ->
  build dst path -> check skip condition -> append to files_to_convert

We test the logic in isolation using the CLI's is_safe_path helper and
by replaying the same conditions with real temp directories.
"""

import os
import time
from pathlib import Path

import pytest

import terminal.cli_converter as cli_mod

is_safe_path = cli_mod.is_safe_path
SUPPORTED = cli_mod.SUPPORTED_EXTENSIONS  # set of lowercase ".ext" strings


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _collect_files(input_dir: Path, output_dir: Path, selected_exts, force=False):
    """
    Replicate the CLI file-collection loop without any I/O or printing.
    Returns (files_to_convert list, skipped count).
    """
    files_to_convert = []
    skipped = 0

    for root, _, files in os.walk(input_dir):
        for file in files:
            src_path = Path(root) / file

            if not is_safe_path(input_dir, src_path):
                continue
            if src_path.suffix.lower() not in selected_exts:
                continue

            rel = src_path.relative_to(input_dir)
            dst_path = output_dir / rel.with_suffix(".md")

            if not is_safe_path(output_dir, dst_path):
                continue

            if dst_path.exists() and not force:
                if dst_path.stat().st_mtime >= src_path.stat().st_mtime:
                    skipped += 1
                    continue

            files_to_convert.append((src_path, dst_path))

    return files_to_convert, skipped


# ═══════════════════════════════════════════════════════════════════════════════
# File discovery
# ═══════════════════════════════════════════════════════════════════════════════

class TestFileWalk:
    """Collection correctly discovers files in flat and nested directories."""

    def test_file_walk_finds_flat_files(self, tmp_path):
        """Files directly in input_dir are discovered."""
        inp = tmp_path / "input"
        out = tmp_path / "output"
        inp.mkdir(); out.mkdir()
        (inp / "a.csv").write_text("a,b\n", encoding="utf-8")
        (inp / "b.html").write_text("<html></html>", encoding="utf-8")

        found, _ = _collect_files(inp, out, {".csv", ".html"})
        assert len(found) == 2, f"Expected 2 files, found {len(found)}"

    def test_file_walk_finds_nested_files(self, tmp_path):
        """Files in subdirectories are discovered recursively."""
        inp = tmp_path / "input"
        out = tmp_path / "output"
        inp.mkdir(); out.mkdir()
        sub = inp / "subdir" / "deep"
        sub.mkdir(parents=True)
        (sub / "nested.csv").write_text("x\n", encoding="utf-8")

        found, _ = _collect_files(inp, out, {".csv"})
        assert len(found) == 1
        assert found[0][0].name == "nested.csv"

    def test_file_walk_empty_folder(self, tmp_path):
        """An empty input directory produces zero files and zero skipped."""
        inp = tmp_path / "input"
        out = tmp_path / "output"
        inp.mkdir(); out.mkdir()

        found, skipped = _collect_files(inp, out, {".csv", ".pdf"})
        assert found == [], "Empty dir should yield no files"
        assert skipped == 0

    def test_file_walk_no_matching_extensions(self, tmp_path):
        """Files present but no extension overlap yields zero files."""
        inp = tmp_path / "input"
        out = tmp_path / "output"
        inp.mkdir(); out.mkdir()
        (inp / "archive.zip").write_bytes(b"PK\x03\x04")
        (inp / "script.py").write_text("pass", encoding="utf-8")

        found, _ = _collect_files(inp, out, {".csv", ".pdf"})
        assert found == []


# ═══════════════════════════════════════════════════════════════════════════════
# Extension filtering
# ═══════════════════════════════════════════════════════════════════════════════

class TestExtensionFiltering:
    """Only selected extensions are returned from collection."""

    def test_only_selected_extensions_collected(self, tmp_path):
        """Files with non-selected extensions are ignored."""
        inp = tmp_path / "input"
        out = tmp_path / "output"
        inp.mkdir(); out.mkdir()
        (inp / "keep.csv").write_text("a\n", encoding="utf-8")
        (inp / "ignore.html").write_text("<html/>\n", encoding="utf-8")

        found, _ = _collect_files(inp, out, {".csv"})
        assert len(found) == 1
        assert found[0][0].suffix == ".csv"

    def test_multiple_extensions_all_collected(self, tmp_path):
        """When multiple extensions are selected, all matching files are collected."""
        inp = tmp_path / "input"
        out = tmp_path / "output"
        inp.mkdir(); out.mkdir()
        for ext in (".csv", ".html", ".json"):
            (inp / f"file{ext}").write_text("content", encoding="utf-8")

        found, _ = _collect_files(inp, out, {".csv", ".html", ".json"})
        assert len(found) == 3


# ═══════════════════════════════════════════════════════════════════════════════
# Skip logic (up-to-date detection)
# ═══════════════════════════════════════════════════════════════════════════════

class TestSkipLogic:
    """Up-to-date output files are skipped; force flag overrides this."""

    def test_skip_when_output_is_newer(self, tmp_path):
        """A destination .md file newer than its source is skipped."""
        inp = tmp_path / "input"; out = tmp_path / "output"
        inp.mkdir(); out.mkdir()

        src = inp / "doc.csv"
        src.write_text("a,b\n", encoding="utf-8")
        dst = out / "doc.md"
        dst.write_text("# already done", encoding="utf-8")

        # Make dst newer than src by nudging its mtime forward
        future = src.stat().st_mtime + 10
        os.utime(dst, (future, future))

        found, skipped = _collect_files(inp, out, {".csv"}, force=False)
        assert len(found) == 0, "File should be skipped (output is newer)"
        assert skipped == 1

    def test_convert_when_source_is_newer(self, tmp_path):
        """When source is newer than destination, it should be converted."""
        inp = tmp_path / "input"; out = tmp_path / "output"
        inp.mkdir(); out.mkdir()

        dst = out / "doc.md"
        dst.write_text("# old output", encoding="utf-8")
        old_mtime = dst.stat().st_mtime

        # Write source *after* destination — it will be newer
        src = inp / "doc.csv"
        src.write_text("a,b\n", encoding="utf-8")

        # Artificially make src newer
        future = dst.stat().st_mtime + 10
        os.utime(src, (future, future))

        found, skipped = _collect_files(inp, out, {".csv"}, force=False)
        assert len(found) == 1, "Newer source should trigger re-conversion"
        assert skipped == 0

    def test_force_flag_overrides_skip(self, tmp_path):
        """force=True causes all files to be collected regardless of output age."""
        inp = tmp_path / "input"; out = tmp_path / "output"
        inp.mkdir(); out.mkdir()

        src = inp / "doc.csv"
        src.write_text("a,b\n", encoding="utf-8")
        dst = out / "doc.md"
        dst.write_text("# old", encoding="utf-8")
        future = src.stat().st_mtime + 100
        os.utime(dst, (future, future))

        found, skipped = _collect_files(inp, out, {".csv"}, force=True)
        assert len(found) == 1, "Force flag must override skip logic"
        assert skipped == 0

    def test_no_output_file_always_collected(self, tmp_path):
        """A source file with no existing output is always collected."""
        inp = tmp_path / "input"; out = tmp_path / "output"
        inp.mkdir(); out.mkdir()

        (inp / "new.csv").write_text("a\n", encoding="utf-8")
        # No corresponding .md in output

        found, skipped = _collect_files(inp, out, {".csv"}, force=False)
        assert len(found) == 1
        assert skipped == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Output path building
# ═══════════════════════════════════════════════════════════════════════════════

class TestOutputPathBuilding:
    """Output paths correctly mirror the input directory structure."""

    def test_relative_path_mirrors_input_structure(self, tmp_path):
        """A file at input/a/b/file.csv maps to output/a/b/file.md."""
        inp = tmp_path / "input"; out = tmp_path / "output"
        inp.mkdir(); out.mkdir()
        sub = inp / "a" / "b"
        sub.mkdir(parents=True)
        (sub / "file.csv").write_text("x\n", encoding="utf-8")

        found, _ = _collect_files(inp, out, {".csv"})
        assert len(found) == 1
        src, dst = found[0]
        expected_dst = out / "a" / "b" / "file.md"
        assert dst == expected_dst, (
            f"Expected dst {expected_dst}, got {dst}"
        )

    def test_extension_changed_to_md(self, tmp_path):
        """Output file always has .md extension regardless of source extension."""
        inp = tmp_path / "input"; out = tmp_path / "output"
        inp.mkdir(); out.mkdir()
        (inp / "report.html").write_text("<html/>", encoding="utf-8")

        found, _ = _collect_files(inp, out, {".html"})
        assert len(found) == 1
        _, dst = found[0]
        assert dst.suffix == ".md", f"Output suffix should be .md, got {dst.suffix}"
        assert dst.stem == "report"

    def test_flat_input_flat_output(self, tmp_path):
        """Files at the root of input_dir map directly to the root of output_dir."""
        inp = tmp_path / "input"; out = tmp_path / "output"
        inp.mkdir(); out.mkdir()
        (inp / "plain.csv").write_text("a\n", encoding="utf-8")

        found, _ = _collect_files(inp, out, {".csv"})
        assert len(found) == 1
        _, dst = found[0]
        assert dst.parent == out, f"Flat input should produce flat output, got parent {dst.parent}"

    def test_multiple_nested_depths_preserved(self, tmp_path):
        """Depth of nesting is preserved in output paths for all files."""
        inp = tmp_path / "input"; out = tmp_path / "output"
        inp.mkdir(); out.mkdir()
        (inp / "top.csv").write_text("a\n", encoding="utf-8")
        mid = inp / "mid"; mid.mkdir()
        (mid / "mid.csv").write_text("b\n", encoding="utf-8")
        deep = inp / "mid" / "deep"; deep.mkdir()
        (deep / "deep.csv").write_text("c\n", encoding="utf-8")

        found, _ = _collect_files(inp, out, {".csv"})
        dsts = {dst for _, dst in found}

        assert out / "top.md" in dsts
        assert out / "mid" / "mid.md" in dsts
        assert out / "mid" / "deep" / "deep.md" in dsts
