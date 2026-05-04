"""
Tests for extension allowlist consistency, filtering, and safety.

Both modules expose SUPPORTED_EXTENSIONS — the CLI as a set, the GUI as a list.
These tests verify:
  - The two lists are equivalent (no divergence)
  - Dangerous types are absent
  - Expected common formats are present
  - Extension matching is case-insensitive in usage
  - .zip is not included (was explicitly removed)
"""

import pytest

import terminal.cli_converter as cli_mod
import gui.gui_converter as gui_mod

# Normalise to sets of lowercase strings for comparison
CLI_EXTS = {e.lower() for e in cli_mod.SUPPORTED_EXTENSIONS}
GUI_EXTS = {e.lower() for e in gui_mod.SUPPORTED_EXTENSIONS}

# Expected exact count across both modules (24 types, no .zip)
EXPECTED_COUNT = 24


# ═══════════════════════════════════════════════════════════════════════════════
# Allowlist integrity
# ═══════════════════════════════════════════════════════════════════════════════

class TestAllowlistIntegrity:
    """The two SUPPORTED_EXTENSIONS collections must be identical."""

    def test_gui_cli_extensions_match(self):
        """GUI and CLI must expose exactly the same set of extensions."""
        assert CLI_EXTS == GUI_EXTS, (
            f"Mismatch between CLI and GUI extension lists.\n"
            f"CLI only: {CLI_EXTS - GUI_EXTS}\n"
            f"GUI only: {GUI_EXTS - CLI_EXTS}"
        )

    def test_extension_list_count(self):
        """Both modules must list exactly {count} supported extensions."""
        assert len(CLI_EXTS) == EXPECTED_COUNT, (
            f"CLI has {len(CLI_EXTS)} extensions, expected {EXPECTED_COUNT}"
        )
        assert len(GUI_EXTS) == EXPECTED_COUNT, (
            f"GUI has {len(GUI_EXTS)} extensions, expected {EXPECTED_COUNT}"
        )

    def test_all_extensions_start_with_dot(self):
        """Every entry must begin with '.' (e.g. '.pdf', not 'pdf')."""
        for ext in CLI_EXTS:
            assert ext.startswith("."), f"CLI extension '{ext}' missing leading dot"
        for ext in GUI_EXTS:
            assert ext.startswith("."), f"GUI extension '{ext}' missing leading dot"

    def test_no_duplicates_in_gui_list(self):
        """The GUI list (not set) should not contain duplicate entries."""
        raw = [e.lower() for e in gui_mod.SUPPORTED_EXTENSIONS]
        assert len(raw) == len(set(raw)), (
            f"GUI SUPPORTED_EXTENSIONS contains duplicates: "
            f"{[e for e in raw if raw.count(e) > 1]}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Safety: dangerous extensions excluded
# ═══════════════════════════════════════════════════════════════════════════════

class TestDangerousExtensionsAbsent:
    """Executable and script types must never appear in the allowlist."""

    DANGEROUS = [".exe", ".dll", ".ps1", ".bat", ".cmd", ".py", ".sh", ".msi", ".vbs", ".js"]

    @pytest.mark.parametrize("ext", DANGEROUS)
    def test_dangerous_extension_not_in_cli(self, ext):
        """CLI allowlist must not include dangerous extension."""
        assert ext not in CLI_EXTS, f"Dangerous extension '{ext}' found in CLI list"

    @pytest.mark.parametrize("ext", DANGEROUS)
    def test_dangerous_extension_not_in_gui(self, ext):
        """GUI allowlist must not include dangerous extension."""
        assert ext not in GUI_EXTS, f"Dangerous extension '{ext}' found in GUI list"


# ═══════════════════════════════════════════════════════════════════════════════
# Safety: .zip explicitly excluded
# ═══════════════════════════════════════════════════════════════════════════════

class TestZipExcluded:
    """ZIP archives must not be in the allowlist (security fix)."""

    def test_zip_not_in_cli_extensions(self):
        """CLI must not support .zip files."""
        assert ".zip" not in CLI_EXTS, ".zip must NOT be in CLI SUPPORTED_EXTENSIONS"

    def test_zip_not_in_gui_extensions(self):
        """GUI must not support .zip files."""
        assert ".zip" not in GUI_EXTS, ".zip must NOT be in GUI SUPPORTED_EXTENSIONS"


# ═══════════════════════════════════════════════════════════════════════════════
# Common formats present
# ═══════════════════════════════════════════════════════════════════════════════

class TestCommonFormatsPresent:
    """Core document and media types that users depend on must be present."""

    REQUIRED = [".pdf", ".docx", ".xlsx", ".pptx", ".csv", ".html", ".jpg", ".png"]

    @pytest.mark.parametrize("ext", REQUIRED)
    def test_required_extension_in_cli(self, ext):
        """CLI must support common format."""
        assert ext in CLI_EXTS, f"Expected extension '{ext}' missing from CLI list"

    @pytest.mark.parametrize("ext", REQUIRED)
    def test_required_extension_in_gui(self, ext):
        """GUI must support common format."""
        assert ext in GUI_EXTS, f"Expected extension '{ext}' missing from GUI list"


# ═══════════════════════════════════════════════════════════════════════════════
# Case-insensitive filtering behaviour
# ═══════════════════════════════════════════════════════════════════════════════

class TestExtensionCaseSensitivity:
    """File extension matching should be case-insensitive during conversion."""

    def test_uppercase_ext_matches_allowlist(self):
        """A .PDF file should be accepted because its lower() is in the allowlist."""
        # Simulate what the CLI does: src_path.suffix.lower() in supported_extensions
        uppercase_suffix = ".PDF"
        assert uppercase_suffix.lower() in CLI_EXTS, (
            ".PDF should match .pdf in the allowlist via lower()"
        )

    def test_mixed_case_ext_matches(self):
        """A .Docx suffix normalized to lower case matches the allowlist."""
        assert ".Docx".lower() in CLI_EXTS

    def test_csv_uppercase_matches(self):
        """A .CSV file should be accepted."""
        assert ".CSV".lower() in CLI_EXTS


# ═══════════════════════════════════════════════════════════════════════════════
# Extension filtering in file collection
# ═══════════════════════════════════════════════════════════════════════════════

class TestExtensionFiltering:
    """Verify that the extension filter logic correctly includes/excludes files."""

    def test_supported_file_passes_filter(self, tmp_path):
        """A .csv file is included when .csv is in the selected set."""
        f = tmp_path / "data.csv"
        f.write_text("a,b\n1,2\n", encoding="utf-8")

        selected = {".csv"}
        passes = f.suffix.lower() in selected
        assert passes is True

    def test_unsupported_file_blocked_by_filter(self, tmp_path):
        """A .zip file is excluded when .zip is not in the selected set."""
        f = tmp_path / "archive.zip"
        f.write_bytes(b"PK\x03\x04")  # minimal ZIP magic bytes

        selected = CLI_EXTS  # zip not in here
        passes = f.suffix.lower() in selected
        assert passes is False, ".zip should be blocked by the allowlist"

    def test_unknown_extension_blocked(self, tmp_path):
        """A completely unknown extension is blocked."""
        f = tmp_path / "weird.xyz"
        f.write_text("content", encoding="utf-8")

        passes = f.suffix.lower() in CLI_EXTS
        assert passes is False

    def test_no_extension_file_blocked(self, tmp_path):
        """A file with no extension is blocked."""
        f = tmp_path / "Makefile"
        f.write_text("all:", encoding="utf-8")

        # suffix returns "" for files with no extension
        passes = f.suffix.lower() in CLI_EXTS
        assert passes is False

    def test_unsupported_extensions_warning_logic(self):
        """Unsupported extensions produce a non-empty 'unsupported' set."""
        requested = {".pdf", ".zip", ".exe", ".csv"}
        unsupported = requested - CLI_EXTS
        assert ".zip" in unsupported
        assert ".exe" in unsupported
        assert ".pdf" not in unsupported
        assert ".csv" not in unsupported
