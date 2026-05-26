"""
Tests for markitdown API contract compatibility.

These tests verify the exact API surface the app depends on:
  1. MarkItDown is importable
  2. MarkItDown() instantiates without required arguments
  3. .convert() returns an object with .text_content (str)

These tests run on every push (regression guard) and are also run
in isolation by the weekly dependency-check workflow when testing
a new markitdown version.
"""

import pytest


class TestMarkItDownCompat:
    """markitdown API contract tests."""

    def test_markitdown_importable(self):
        """MarkItDown class is importable from markitdown module."""
        from markitdown import MarkItDown
        assert MarkItDown is not None

    def test_instantiates_without_args(self):
        """MarkItDown() instantiates without any required arguments."""
        from markitdown import MarkItDown
        md = MarkItDown()
        assert md is not None

    def test_convert_returns_text_content(self, tmp_path):
        """MarkItDown().convert() returns object with .text_content attribute (str)."""
        f = tmp_path / "test.csv"
        f.write_text("name,value\ntest,42\n", encoding="utf-8")

        from markitdown import MarkItDown
        md = MarkItDown()
        result = md.convert(str(f))

        # The only attributes we depend on
        assert hasattr(result, "text_content"), "Result must have text_content attribute"
        assert isinstance(result.text_content, str), "text_content must be a string"
        assert len(result.text_content) > 0, "text_content must not be empty for valid CSV"
