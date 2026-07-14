"""Tests for markitdown API contract compatibility (ported from the old
tests/test_markitdown_compat.py, unchanged in substance - core/engine.py
depends on exactly this surface: MarkItDown() with no required args and
.convert() returning an object with a str .text_content attribute).

Marks: pytest.mark.integration - these perform real file I/O + conversion.
"""

import pytest


@pytest.mark.integration
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

        assert hasattr(result, "text_content"), "Result must have text_content attribute"
        assert isinstance(result.text_content, str), "text_content must be a string"
        assert len(result.text_content) > 0, "text_content must not be empty for valid CSV"
