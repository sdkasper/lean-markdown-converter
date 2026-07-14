"""Fixtures specific to tests/core/.

Root tests/conftest.py already provides temp_input_dir, temp_output_dir,
fixture_pdf/docx/csv/html, sample_config, etc. - those apply here too.
This file only adds what's needed on top: a fake MarkItDown-shaped object
and a ConversionTask factory helper.
"""

from pathlib import Path

import pytest

from core.scanner import ConversionTask


class _FakeResult:
    """Stand-in for markitdown's DocumentConverterResult."""

    def __init__(self, text_content):
        self.text_content = text_content


class _FakeMarkItDown:
    """Fake md object: convert() returns canned text or raises, per path.

    Configure via ``responses`` (dict of str(src) -> text_content) and/or
    ``raises`` (dict of str(src) -> exception instance/class). Any source
    not found in either mapping falls back to ``default_text``.
    """

    def __init__(self, responses=None, raises=None, default_text="converted content"):
        self.responses = responses or {}
        self.raises = raises or {}
        self.default_text = default_text
        self.calls = []

    def convert(self, path):
        self.calls.append(path)
        if path in self.raises:
            exc = self.raises[path]
            raise exc if isinstance(exc, BaseException) else exc()
        text = self.responses.get(path, self.default_text)
        return _FakeResult(text)


@pytest.fixture
def fake_md():
    """Factory fixture: fake_md() -> a fresh _FakeMarkItDown instance.

    Call with kwargs to configure canned responses/exceptions, e.g.:
        md = fake_md(responses={"/a.csv": ""}, raises={"/b.pdf": ValueError("boom")})
    """
    def _make(**kwargs):
        return _FakeMarkItDown(**kwargs)
    return _make


@pytest.fixture
def make_task(tmp_path):
    """Factory fixture: build a ConversionTask with sensible defaults.

    make_task(name="a.csv", content="hello", existed=False, dst_name=None)
    Creates the source file under tmp_path/src/<name> with the given content
    (skip creation by passing content=None) and returns a ConversionTask
    pointing at tmp_path/dst/<dst_name or name-with-.md-suffix>.
    """
    def _make(name="file.csv", content="hello", existed=False, dst_name=None):
        src_dir = tmp_path / "src"
        dst_dir = tmp_path / "dst"
        src_dir.mkdir(exist_ok=True)
        dst_dir.mkdir(exist_ok=True)

        src = src_dir / name
        if content is not None:
            src.write_text(content, encoding="utf-8")

        dst = dst_dir / (dst_name or (Path(name).stem + ".md"))
        if existed:
            dst.write_text("# pre-existing", encoding="utf-8")

        return ConversionTask(src=src, dst=dst, existed=existed)

    return _make
