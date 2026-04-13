"""Tests for the PatchGenerator class."""

import pytest
from sandbox.patcher import PatchGenerator
from models import PatchResult


class TestGenerateDiff:
    """Tests for PatchGenerator.generate_diff."""

    def setup_method(self):
        self.pg = PatchGenerator()

    def test_identical_strings_produce_empty_diff(self):
        code = "def foo():\n    return 1\n"
        diff = self.pg.generate_diff(code, code)
        assert diff == ""

    def test_single_line_change(self):
        original = "def foo():\n    return 1\n"
        modified = "def foo():\n    return 2\n"
        diff = self.pg.generate_diff(original, modified)
        assert "-    return 1" in diff
        assert "+    return 2" in diff

    def test_added_lines(self):
        original = "a\n"
        modified = "a\nb\n"
        diff = self.pg.generate_diff(original, modified)
        assert "+b" in diff

    def test_removed_lines(self):
        original = "a\nb\n"
        modified = "a\n"
        diff = self.pg.generate_diff(original, modified)
        assert "-b" in diff

    def test_empty_to_content(self):
        diff = self.pg.generate_diff("", "hello\n")
        assert "+hello" in diff

    def test_content_to_empty(self):
        diff = self.pg.generate_diff("hello\n", "")
        assert "-hello" in diff


class TestApplyPatch:
    """Tests for PatchGenerator.apply_patch."""

    def setup_method(self):
        self.pg = PatchGenerator()

    def test_empty_diff_returns_original(self):
        code = "def foo():\n    return 1\n"
        result = self.pg.apply_patch(code, "")
        assert result.success is True
        assert result.patched_code == code

    def test_whitespace_only_diff_returns_original(self):
        code = "x = 1\n"
        result = self.pg.apply_patch(code, "   \n  \n")
        assert result.success is True
        assert result.patched_code == code

    def test_round_trip_single_line_change(self):
        original = "def foo():\n    return 1\n"
        modified = "def foo():\n    return 2\n"
        diff = self.pg.generate_diff(original, modified)
        result = self.pg.apply_patch(original, diff)
        assert result.success is True
        assert result.patched_code == modified

    def test_round_trip_multiline_change(self):
        original = "a\nb\nc\nd\n"
        modified = "a\nx\ny\nd\n"
        diff = self.pg.generate_diff(original, modified)
        result = self.pg.apply_patch(original, diff)
        assert result.success is True
        assert result.patched_code == modified

    def test_round_trip_add_lines(self):
        original = "line1\nline3\n"
        modified = "line1\nline2\nline3\n"
        diff = self.pg.generate_diff(original, modified)
        result = self.pg.apply_patch(original, diff)
        assert result.success is True
        assert result.patched_code == modified

    def test_round_trip_remove_lines(self):
        original = "line1\nline2\nline3\n"
        modified = "line1\nline3\n"
        diff = self.pg.generate_diff(original, modified)
        result = self.pg.apply_patch(original, diff)
        assert result.success is True
        assert result.patched_code == modified

    def test_preserves_unchanged_lines(self):
        original = "header\na\nb\nc\nfooter\n"
        modified = "header\na\nX\nc\nfooter\n"
        diff = self.pg.generate_diff(original, modified)
        result = self.pg.apply_patch(original, diff)
        assert result.success is True
        lines = result.patched_code.splitlines()
        assert lines[0] == "header"
        assert lines[1] == "a"
        assert lines[3] == "c"
        assert lines[4] == "footer"

    def test_mismatched_diff_returns_failure(self):
        original = "def foo():\n    return 1\n"
        wrong_original = "def bar():\n    return 99\n"
        modified = "def bar():\n    return 100\n"
        diff = self.pg.generate_diff(wrong_original, modified)
        result = self.pg.apply_patch(original, diff)
        assert result.success is False
        assert result.error_message is not None
        assert len(result.error_message) > 0

    def test_invalid_diff_format_returns_failure(self):
        result = self.pg.apply_patch("code\n", "@@ invalid hunk @@\n")
        assert result.success is False
        assert result.error_message is not None

    def test_returns_patch_result_type(self):
        result = self.pg.apply_patch("x\n", "")
        assert isinstance(result, PatchResult)

    def test_no_trailing_newline_preserved(self):
        original = "def foo():\n    return 1"
        modified = "def foo():\n    return 2"
        diff = self.pg.generate_diff(original, modified)
        result = self.pg.apply_patch(original, diff)
        assert result.success is True
        assert result.patched_code == modified
