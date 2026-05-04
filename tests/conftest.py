"""
Shared pytest fixtures for the lp-bulk-markdown-converter test suite.

All fixtures use tmp_path (pytest built-in) so they are fully isolated
and cleaned up automatically after each test.
"""

import json
import shutil
from pathlib import Path

import pytest

# Absolute path to the fixtures/ directory next to this file.
FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ─── DIRECTORY FIXTURES ──────────────────────────────────────────────────────

@pytest.fixture
def temp_input_dir(tmp_path):
    """A temporary input directory pre-populated with one file per supported type."""
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    # Plain-text files that MarkItDown handles natively
    (input_dir / "note.csv").write_text("col1,col2\nval1,val2\n", encoding="utf-8")
    (input_dir / "page.html").write_text(
        "<html><body><h1>Hi</h1></body></html>", encoding="utf-8"
    )
    (input_dir / "data.json").write_text('{"key": "value"}', encoding="utf-8")

    # Binary fixtures copied from the fixtures/ folder
    for name in ("sample.pdf", "sample.csv", "sample.html", "sample.json", "sample.docx"):
        src = FIXTURES_DIR / name
        if src.exists():
            shutil.copy(src, input_dir / name)

    return input_dir


@pytest.fixture
def temp_output_dir(tmp_path):
    """An empty temporary output directory."""
    out = tmp_path / "output"
    out.mkdir()
    return out


# ─── CONFIG FIXTURES ─────────────────────────────────────────────────────────

@pytest.fixture
def sample_config(temp_input_dir, temp_output_dir):
    """A complete, valid config dict that both CLI and GUI would produce."""
    return {
        "input_folder": str(temp_input_dir),
        "output_folder": str(temp_output_dir),
        "extensions": {
            ".csv": True,
            ".html": True,
            ".pdf": False,
            ".docx": True,
        },
        "force": False,
        "dry_run": False,
        "logging": True,
    }


@pytest.fixture
def corrupted_config(tmp_path):
    """Path to a config file whose content is not valid JSON."""
    cfg_path = tmp_path / "bad_config.json"
    cfg_path.write_text("{this is : not valid json ][", encoding="utf-8")
    return cfg_path


@pytest.fixture
def config_file_path(tmp_path, sample_config):
    """Write sample_config to disk and return the path."""
    cfg_path = tmp_path / "conversion_config.json"
    cfg_path.write_text(json.dumps(sample_config, indent=4), encoding="utf-8")
    return cfg_path


# ─── FILE HELPER FIXTURES ────────────────────────────────────────────────────

@pytest.fixture
def create_test_file():
    """
    Factory fixture: returns a helper that creates a file at ``path``
    with the given ``content`` (str, utf-8).
    """
    def _make(path: Path, content: str = "test content") -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    return _make


@pytest.fixture
def sample_files(tmp_path):
    """
    A dict of ready-made small test files, keyed by extension.
    These are plain text so they can be created without binary fixtures.
    """
    files = {}

    csv_file = tmp_path / "test.csv"
    csv_file.write_text("a,b,c\n1,2,3\n4,5,6\n", encoding="utf-8")
    files[".csv"] = csv_file

    html_file = tmp_path / "test.html"
    html_file.write_text("<html><body><p>Hello</p></body></html>", encoding="utf-8")
    files[".html"] = html_file

    json_file = tmp_path / "test.json"
    json_file.write_text('{"hello": "world"}', encoding="utf-8")
    files[".json"] = json_file

    return files


# ─── REAL FIXTURE PATHS ──────────────────────────────────────────────────────

@pytest.fixture
def fixture_pdf():
    """Absolute path to the sample PDF fixture."""
    p = FIXTURES_DIR / "sample.pdf"
    assert p.exists(), f"Fixture not found: {p}"
    return p


@pytest.fixture
def fixture_docx():
    """Absolute path to the sample DOCX fixture."""
    p = FIXTURES_DIR / "sample.docx"
    assert p.exists(), f"Fixture not found: {p}"
    return p


@pytest.fixture
def fixture_csv():
    """Absolute path to the sample CSV fixture."""
    p = FIXTURES_DIR / "sample.csv"
    assert p.exists(), f"Fixture not found: {p}"
    return p


@pytest.fixture
def fixture_html():
    """Absolute path to the sample HTML fixture."""
    p = FIXTURES_DIR / "sample.html"
    assert p.exists(), f"Fixture not found: {p}"
    return p
