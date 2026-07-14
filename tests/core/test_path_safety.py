"""Tests for core/paths.py path-safety primitive (is_safe_path).

Ported from the old tests/test_path_safety.py, which parametrized over the
duplicated CLI/GUI implementations. In v2.0.0 there is a single
implementation (core.paths.is_safe_path), so no parametrization is needed.

Security marks: pytest.mark.security (NFR-001: path traversal prevention).
"""

import os
import sys

import pytest

from core.paths import is_safe_path


# ═══════════════════════════════════════════════════════════════════════════
# Core containment logic
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.security
class TestIsSafePathCore:
    def test_valid_child_path_is_safe(self, tmp_path):
        child = tmp_path / "subdir" / "file.txt"
        assert is_safe_path(tmp_path, child) is True

    def test_base_dir_itself_is_safe(self, tmp_path):
        assert is_safe_path(tmp_path, tmp_path) is True

    def test_deep_nesting_is_safe(self, tmp_path):
        deep = tmp_path / "a" / "b" / "c" / "d" / "e" / "file.md"
        assert is_safe_path(tmp_path, deep) is True

    def test_absolute_path_outside_root_is_rejected(self, tmp_path):
        outside = tmp_path.parent / "other_dir" / "evil.txt"
        assert is_safe_path(tmp_path, outside) is False

    def test_sibling_directory_is_rejected(self, tmp_path):
        sibling = tmp_path.parent / "sibling"
        assert is_safe_path(tmp_path, sibling) is False

    def test_parent_directory_traversal_rejected(self, tmp_path):
        traversal = tmp_path / "sub" / ".." / ".." / "evil"
        assert is_safe_path(tmp_path, traversal) is False

    def test_nonexistent_target_inside_base_is_safe(self, tmp_path):
        """resolve(strict=False) semantics: a target that doesn't exist yet
        (typical for a not-yet-written output .md file) is still evaluated
        purely on lexical/containment grounds, not existence."""
        target = tmp_path / "does" / "not" / "exist.md"
        assert not target.exists()
        assert is_safe_path(tmp_path, target) is True

    def test_nonexistent_target_outside_base_is_rejected(self, tmp_path):
        target = tmp_path.parent / "does_not_exist_either" / "evil.md"
        assert not target.exists()
        assert is_safe_path(tmp_path, target) is False

    def test_nonexistent_base_dir_handled(self, tmp_path):
        """base_dir itself not existing must not raise — resolve(strict=False)
        still allows a lexical containment check."""
        missing_base = tmp_path / "missing_base"
        child = missing_base / "file.txt"
        assert is_safe_path(missing_base, child) is True


# ═══════════════════════════════════════════════════════════════════════════
# Symlink-specific tests (Windows junction / POSIX symlink)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.security
class TestSymlinkTraversal:
    @pytest.mark.skipif(
        sys.platform == "win32" and not os.path.exists("C:/Windows"),
        reason="Symlink creation may require elevated privileges on Windows",
    )
    def test_symlink_pointing_outside_is_rejected(self, tmp_path):
        outside_dir = tmp_path.parent / "outside_target"
        outside_dir.mkdir(exist_ok=True)
        outside_file = outside_dir / "secret.txt"
        outside_file.write_text("secret", encoding="utf-8")

        base = tmp_path / "base"
        base.mkdir()

        link = base / "evil_link"
        try:
            link.symlink_to(outside_dir)
        except (OSError, NotImplementedError):
            pytest.skip("Cannot create symlinks in this environment")

        target = link / "secret.txt"
        assert is_safe_path(base, target) is False

    @pytest.mark.skipif(
        sys.platform == "win32" and not os.path.exists("C:/Windows"),
        reason="Symlink creation may require elevated privileges on Windows",
    )
    def test_symlink_within_base_is_safe(self, tmp_path):
        base = tmp_path / "base"
        base.mkdir()
        target_dir = base / "real_dir"
        target_dir.mkdir()

        link = base / "link_to_real"
        try:
            link.symlink_to(target_dir)
        except (OSError, NotImplementedError):
            pytest.skip("Cannot create symlinks in this environment")

        assert is_safe_path(base, link / "file.txt") is True
