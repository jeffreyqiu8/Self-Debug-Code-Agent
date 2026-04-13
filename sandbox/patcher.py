"""Patch generator for applying unified diffs to code strings.

Uses Python's difflib for generating unified diffs and a custom applicator
for applying them. All code lives in memory as strings — no filesystem-based
patch tools are needed.
"""

import difflib
import re
from models import PatchResult


class PatchGenerator:
    """Generates and applies unified diffs on in-memory code strings."""

    def generate_diff(self, original: str, modified: str) -> str:
        """Generate a unified diff between two code strings using difflib.

        Args:
            original: The original code string.
            modified: The modified code string.

        Returns:
            A unified diff string. Empty string if the inputs are identical.
        """
        original_lines = original.splitlines(keepends=True)
        modified_lines = modified.splitlines(keepends=True)

        # Ensure both line lists end with newlines for clean diffs
        if original_lines and not original_lines[-1].endswith("\n"):
            original_lines[-1] += "\n"
        if modified_lines and not modified_lines[-1].endswith("\n"):
            modified_lines[-1] += "\n"

        diff_lines = list(
            difflib.unified_diff(
                original_lines,
                modified_lines,
                fromfile="original",
                tofile="modified",
            )
        )
        return "".join(diff_lines)

    def apply_patch(self, original_code: str, unified_diff: str) -> PatchResult:
        """Parse a unified diff and apply it to the original code string.

        Args:
            original_code: The original source code.
            unified_diff: A unified diff string to apply.

        Returns:
            PatchResult with patched_code on success, or error_message on failure.
        """
        if not unified_diff or not unified_diff.strip():
            return PatchResult(success=True, patched_code=original_code)

        try:
            hunks = _parse_unified_diff(unified_diff)
        except ValueError as e:
            return PatchResult(
                success=False,
                error_message=f"Failed to parse unified diff: {e}",
            )

        if not hunks:
            return PatchResult(success=True, patched_code=original_code)

        original_lines = original_code.splitlines(keepends=True)
        # Ensure trailing newline consistency
        if original_lines and not original_lines[-1].endswith("\n"):
            original_lines[-1] += "\n"

        try:
            patched_lines = _apply_hunks(original_lines, hunks)
        except PatchError as e:
            return PatchResult(
                success=False,
                error_message=f"Failed to apply patch: {e}",
            )

        patched_code = "".join(patched_lines)
        # Preserve original trailing-newline style
        if not original_code.endswith("\n") and patched_code.endswith("\n"):
            patched_code = patched_code.rstrip("\n")

        return PatchResult(success=True, patched_code=patched_code)


class PatchError(Exception):
    """Raised when a patch cannot be applied cleanly."""


def _parse_unified_diff(diff_text: str) -> list[dict]:
    """Parse a unified diff string into a list of hunk dictionaries.

    Each hunk dict contains:
        - orig_start: 1-based start line in the original file
        - orig_count: number of lines from the original
        - mod_start: 1-based start line in the modified file
        - mod_count: number of lines in the modified version
        - changes: list of (tag, line) tuples where tag is ' ', '+', or '-'

    Args:
        diff_text: The unified diff string.

    Returns:
        A list of parsed hunk dictionaries.

    Raises:
        ValueError: If the diff format is invalid.
    """
    hunks: list[dict] = []
    lines = diff_text.splitlines(keepends=True)

    i = 0
    # Skip header lines (---, +++, or any preamble before first @@)
    while i < len(lines):
        stripped = lines[i].rstrip("\n\r")
        if stripped.startswith("@@"):
            break
        i += 1

    while i < len(lines):
        stripped = lines[i].rstrip("\n\r")
        if not stripped.startswith("@@"):
            i += 1
            continue

        # Parse hunk header: @@ -orig_start,orig_count +mod_start,mod_count @@
        match = re.match(
            r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", stripped
        )
        if not match:
            raise ValueError(f"Invalid hunk header: {stripped}")

        orig_start = int(match.group(1))
        orig_count = int(match.group(2)) if match.group(2) is not None else 1
        mod_start = int(match.group(3))
        mod_count = int(match.group(4)) if match.group(4) is not None else 1

        i += 1
        changes: list[tuple[str, str]] = []

        # Read hunk body lines
        while i < len(lines):
            line = lines[i]
            stripped_line = line.rstrip("\n\r")
            if stripped_line.startswith("@@"):
                break  # Next hunk
            if stripped_line.startswith("---") or stripped_line.startswith("+++"):
                i += 1
                continue
            if line.startswith("-"):
                changes.append(("-", line[1:]))
                i += 1
            elif line.startswith("+"):
                changes.append(("+", line[1:]))
                i += 1
            elif line.startswith(" "):
                changes.append((" ", line[1:]))
                i += 1
            elif stripped_line == "\\ No newline at end of file":
                i += 1
            else:
                # Treat as context line (some diffs omit the leading space)
                changes.append((" ", line))
                i += 1

        hunks.append(
            {
                "orig_start": orig_start,
                "orig_count": orig_count,
                "mod_start": mod_start,
                "mod_count": mod_count,
                "changes": changes,
            }
        )

    return hunks


def _normalize(line: str) -> str:
    """Normalize a line for comparison by stripping trailing whitespace."""
    return line.rstrip("\n\r ")


def _apply_hunks(original_lines: list[str], hunks: list[dict]) -> list[str]:
    """Apply parsed hunks to the original lines.

    Processes hunks in order. For each hunk, copies unchanged lines before
    the hunk, then applies the hunk's changes (removing '-' lines, adding
    '+' lines, keeping ' ' context lines).

    Args:
        original_lines: The original file as a list of lines (with newlines).
        hunks: Parsed hunk dictionaries from _parse_unified_diff.

    Returns:
        The patched file as a list of lines.

    Raises:
        PatchError: If context lines don't match the original.
    """
    result: list[str] = []
    orig_idx = 0  # Current position in original_lines (0-based)

    for hunk in hunks:
        hunk_start = hunk["orig_start"] - 1  # Convert to 0-based

        # Copy all unchanged lines before this hunk
        if hunk_start < orig_idx:
            raise PatchError(
                f"Overlapping hunks: hunk starts at line {hunk['orig_start']} "
                f"but we've already processed up to line {orig_idx + 1}"
            )
        result.extend(original_lines[orig_idx:hunk_start])
        orig_idx = hunk_start

        # Apply changes in this hunk
        for tag, line in hunk["changes"]:
            if tag == " ":
                # Context line — verify it matches the original
                if orig_idx >= len(original_lines):
                    raise PatchError(
                        f"Context line at position {orig_idx + 1} is beyond "
                        f"end of file (file has {len(original_lines)} lines)"
                    )
                if _normalize(original_lines[orig_idx]) != _normalize(line):
                    raise PatchError(
                        f"Context mismatch at line {orig_idx + 1}: "
                        f"expected {line.rstrip()!r}, "
                        f"got {original_lines[orig_idx].rstrip()!r}"
                    )
                result.append(original_lines[orig_idx])
                orig_idx += 1
            elif tag == "-":
                # Remove line — verify it matches the original
                if orig_idx >= len(original_lines):
                    raise PatchError(
                        f"Remove line at position {orig_idx + 1} is beyond "
                        f"end of file (file has {len(original_lines)} lines)"
                    )
                if _normalize(original_lines[orig_idx]) != _normalize(line):
                    raise PatchError(
                        f"Remove mismatch at line {orig_idx + 1}: "
                        f"expected {line.rstrip()!r}, "
                        f"got {original_lines[orig_idx].rstrip()!r}"
                    )
                orig_idx += 1  # Skip this line (it's being removed)
            elif tag == "+":
                # Add new line
                if not line.endswith("\n"):
                    line += "\n"
                result.append(line)

    # Copy any remaining lines after the last hunk
    result.extend(original_lines[orig_idx:])

    return result
