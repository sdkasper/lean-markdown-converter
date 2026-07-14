"""Tests for the extension allowlist (TC-005) - the single source of truth
now lives in core/constants.py instead of being duplicated between the CLI
and GUI modules.

Marks: pytest.mark.security for the dangerous-extension-absence checks.
"""

import pytest

from core.constants import AUDIO_EXTENSIONS, EXT_GROUPS, IMAGE_EXTENSIONS, SUPPORTED_EXTENSIONS

EXPECTED_COUNT = 21

REQUIRED = [
    ".csv", ".doc", ".docx", ".epub", ".htm", ".html",
    ".ipynb", ".jpeg", ".jpg", ".json", ".m4a", ".mp3", ".msg", ".pdf",
    ".png", ".ppt", ".pptx", ".wav", ".xls", ".xlsx", ".xml",
]

DANGEROUS = [".exe", ".dll", ".ps1", ".bat", ".zip", ".py", ".msi", ".cmd"]


# ═══════════════════════════════════════════════════════════════════════════════
# Allowlist shape
# ═══════════════════════════════════════════════════════════════════════════════

class TestAllowlistShape:
    """SUPPORTED_EXTENSIONS is the exact expected 21-entry frozenset."""

    def test_exact_count(self):
        assert len(SUPPORTED_EXTENSIONS) == EXPECTED_COUNT, (
            f"Expected {EXPECTED_COUNT} supported extensions, got {len(SUPPORTED_EXTENSIONS)}: "
            f"{sorted(SUPPORTED_EXTENSIONS)}"
        )

    def test_is_frozenset(self):
        assert isinstance(SUPPORTED_EXTENSIONS, frozenset)

    def test_every_entry_starts_with_dot(self):
        for ext in SUPPORTED_EXTENSIONS:
            assert ext.startswith("."), f"'{ext}' is missing its leading dot"

    @pytest.mark.parametrize("ext", REQUIRED)
    def test_all_required_formats_present(self, ext):
        assert ext in SUPPORTED_EXTENSIONS, f"Required extension '{ext}' missing from allowlist"

    def test_no_unexpected_extras(self):
        """Guards against silent additions beyond the documented 21."""
        assert SUPPORTED_EXTENSIONS == frozenset(REQUIRED)


# ═══════════════════════════════════════════════════════════════════════════════
# Dangerous extensions absent (security)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.security
class TestDangerousExtensionsAbsent:
    """Executable/script/archive types must never appear in the allowlist."""

    @pytest.mark.parametrize("ext", DANGEROUS)
    def test_dangerous_extension_excluded(self, ext):
        assert ext not in SUPPORTED_EXTENSIONS, f"Dangerous extension '{ext}' must not be supported"


# ═══════════════════════════════════════════════════════════════════════════════
# EXT_GROUPS <-> SUPPORTED_EXTENSIONS consistency
# ═══════════════════════════════════════════════════════════════════════════════

class TestExtGroupsConsistency:
    """Every grouped extension must be a real supported extension, and the
    union of all groups must equal SUPPORTED_EXTENSIONS exactly (no orphans
    on either side)."""

    def test_every_group_member_is_supported(self):
        for group_name, exts in EXT_GROUPS.items():
            for ext in exts:
                assert ext in SUPPORTED_EXTENSIONS, (
                    f"EXT_GROUPS['{group_name}'] contains '{ext}', not in SUPPORTED_EXTENSIONS"
                )

    def test_union_of_groups_equals_supported_extensions(self):
        union = {ext for exts in EXT_GROUPS.values() for ext in exts}
        assert union == set(SUPPORTED_EXTENSIONS), (
            f"EXT_GROUPS union differs from SUPPORTED_EXTENSIONS.\n"
            f"Only in groups: {union - set(SUPPORTED_EXTENSIONS)}\n"
            f"Only in allowlist: {set(SUPPORTED_EXTENSIONS) - union}"
        )

    def test_no_extension_in_multiple_groups(self):
        seen = {}
        for group_name, exts in EXT_GROUPS.items():
            for ext in exts:
                assert ext not in seen, (
                    f"'{ext}' appears in both '{seen.get(ext)}' and '{group_name}'"
                )
                seen[ext] = group_name


# ═══════════════════════════════════════════════════════════════════════════════
# AUDIO_EXTENSIONS / IMAGE_EXTENSIONS subsets
# ═══════════════════════════════════════════════════════════════════════════════

class TestSubsetConstants:
    """AUDIO_EXTENSIONS and IMAGE_EXTENSIONS must both be proper subsets of
    the full allowlist."""

    def test_audio_extensions_is_subset(self):
        assert AUDIO_EXTENSIONS <= SUPPORTED_EXTENSIONS

    def test_image_extensions_is_subset(self):
        assert IMAGE_EXTENSIONS <= SUPPORTED_EXTENSIONS

    def test_audio_extensions_expected_values(self):
        assert AUDIO_EXTENSIONS == frozenset({".m4a", ".mp3", ".wav"})

    def test_image_extensions_expected_values(self):
        assert IMAGE_EXTENSIONS == frozenset({".jpeg", ".jpg", ".png"})

    def test_audio_and_image_do_not_overlap(self):
        assert AUDIO_EXTENSIONS.isdisjoint(IMAGE_EXTENSIONS)
