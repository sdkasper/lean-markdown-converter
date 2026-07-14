"""Smoke tests for cli/main.py - wiring only.

These tests verify that the interactive CLI calls the core/ API correctly
and drives the expected prompt sequence. They do NOT re-test core business
logic (scanning, path safety, conversion counting, etc.) - that's covered by
tests/core/. Every test drives cli.main.main() directly via a scripted
builtins.input() iterator and captures stdout with capsys.
"""

import json
from pathlib import Path

import pytest

import cli.main
from core.llm_factory import LLMConfigError


# ─── SHARED HELPERS ─────────────────────────────────────────────────────────

def scripted_input(monkeypatch, answers):
    """Patch builtins.input to return *answers* in order, one per call."""
    it = iter(answers)

    def _fake_input(prompt=""):
        try:
            return next(it)
        except StopIteration as exc:
            raise AssertionError(f"Ran out of scripted answers at prompt: {prompt!r}") from exc

    monkeypatch.setattr("builtins.input", _fake_input)


class _FakeResult:
    """Stand-in for markitdown's DocumentConverterResult."""

    def __init__(self, text_content):
        self.text_content = text_content


class _FakeMarkItDown:
    """Fake md object: convert() always returns canned non-empty text."""

    def __init__(self, text="# converted content"):
        self.text = text
        self.calls = []

    def convert(self, path):
        self.calls.append(path)
        return _FakeResult(self.text)


@pytest.fixture(autouse=True)
def patch_environment(monkeypatch, tmp_path):
    """Keep every test off the real project's logs/ and conversion_config.json.

    write_startup_diagnostic/configure_pydub are stubbed to no-ops (per the
    build brief - real binary discovery isn't the CLI's concern to test).
    """
    monkeypatch.setattr(cli.main, "write_startup_diagnostic", lambda: None)
    monkeypatch.setattr(cli.main, "configure_pydub", lambda: False)
    monkeypatch.setattr(cli.main, "logs_dir", lambda: tmp_path / "logs")
    monkeypatch.setattr("core.config.config_file_path", lambda: tmp_path / "conversion_config.json")


@pytest.fixture
def input_dir(tmp_path):
    d = tmp_path / "input"
    d.mkdir()
    (d / "note.csv").write_text("col1,col2\nval1,val2\n", encoding="utf-8")
    return d


@pytest.fixture
def output_dir(tmp_path):
    d = tmp_path / "output"
    d.mkdir()
    return d


# ─── TESTS ──────────────────────────────────────────────────────────────────

def test_happy_path_writes_md_and_prints_summary(monkeypatch, capsys, input_dir, output_dir):
    monkeypatch.setattr(cli.main, "build_markitdown", lambda image_conversion: _FakeMarkItDown())

    scripted_input(monkeypatch, [
        str(input_dir),   # input folder
        str(output_dir),  # output folder
        ".csv",           # extensions
        "n",              # force
        "n",              # logging
        "n",              # dry run
    ])

    cli.main.main()  # should return normally, no SystemExit

    out = capsys.readouterr().out
    assert (output_dir / "note.md").read_text(encoding="utf-8") == "# converted content"
    assert "Converted: 1" in out
    assert "=== Conversion Summary ===" in out


def test_nonexistent_input_reprompts(monkeypatch, capsys, input_dir, output_dir, tmp_path):
    bad_path = tmp_path / "does_not_exist"

    scripted_input(monkeypatch, [
        str(bad_path),    # input folder - doesn't exist, re-prompt
        str(input_dir),   # input folder - accepted
        str(output_dir),  # output folder - accepted
        "bogus",          # extensions - all unsupported, terminates the test quickly
    ])

    with pytest.raises(SystemExit) as exc_info:
        cli.main.main()

    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    assert f"Path does not exist: {bad_path}" in out
    assert "No supported extensions selected" in out


def test_output_folder_created_on_yes(monkeypatch, capsys, input_dir, tmp_path):
    missing_output = tmp_path / "brand_new_output"
    assert not missing_output.exists()

    scripted_input(monkeypatch, [
        str(input_dir),        # input folder
        str(missing_output),   # output folder - doesn't exist
        "y",                   # create it? yes
        "bogus",                # extensions - unsupported, terminates quickly
    ])

    with pytest.raises(SystemExit) as exc_info:
        cli.main.main()

    assert exc_info.value.code == 1
    assert missing_output.is_dir()


def test_unsupported_extension_warned_and_ignored(monkeypatch, capsys, input_dir, output_dir):
    monkeypatch.setattr(cli.main, "build_markitdown", lambda image_conversion: _FakeMarkItDown())

    scripted_input(monkeypatch, [
        str(input_dir),
        str(output_dir),
        "bogus,.csv",     # unsupported + supported
        "n",              # force
        "n",              # logging
        "n",              # dry run
    ])

    cli.main.main()

    out = capsys.readouterr().out
    assert "Warning: Ignoring unsupported extension(s): .bogus" in out
    assert (output_dir / "note.md").exists()


def test_empty_extension_selection_exits_1(monkeypatch, capsys, input_dir, output_dir):
    scripted_input(monkeypatch, [
        str(input_dir),
        str(output_dir),
        "bogus,alsobogus",  # nothing supported
    ])

    with pytest.raises(SystemExit) as exc_info:
        cli.main.main()

    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    assert "No supported extensions selected" in out


def test_dry_run_prints_would_convert_and_exits_without_writing(monkeypatch, capsys, input_dir, output_dir):
    scripted_input(monkeypatch, [
        str(input_dir),
        str(output_dir),
        ".csv",
        "n",   # force
        "n",   # logging
        "y",   # dry run
        "n",   # proceed with actual conversion? no
    ])

    with pytest.raises(SystemExit) as exc_info:
        cli.main.main()

    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "Would convert" in out
    assert not (output_dir / "note.md").exists()


def test_llm_config_error_exits_1_with_message(monkeypatch, capsys, input_dir, output_dir):
    def _raise(image_conversion):
        raise LLMConfigError("gemini requires an API key")

    monkeypatch.setattr(cli.main, "build_markitdown", _raise)

    scripted_input(monkeypatch, [
        str(input_dir),
        str(output_dir),
        ".csv",
        "n",   # force
        "n",   # logging
        "n",   # dry run
    ])

    with pytest.raises(SystemExit) as exc_info:
        cli.main.main()

    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    assert "gemini requires an API key" in out
    assert not (output_dir / "note.md").exists()


def test_config_saved_with_dict_extensions_after_run(monkeypatch, capsys, input_dir, output_dir, tmp_path):
    monkeypatch.setattr(cli.main, "build_markitdown", lambda image_conversion: _FakeMarkItDown())

    scripted_input(monkeypatch, [
        str(input_dir),
        str(output_dir),
        ".csv",
        "n",   # force
        "n",   # logging
        "n",   # dry run
    ])

    cli.main.main()

    saved = json.loads((tmp_path / "conversion_config.json").read_text(encoding="utf-8"))
    assert saved["extensions"] == {".csv": True}
    assert isinstance(saved["extensions"], dict)
