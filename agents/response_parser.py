"""Utilities for extracting structured data from LLM text responses."""

from __future__ import annotations

import re

from models import PatchData


# ---------------------------------------------------------------------------
# Code block helpers
# ---------------------------------------------------------------------------

def extract_code_block(response: str) -> str:
    """Extract Python code from the first markdown code fence in *response*.

    Supports fences with or without a language tag (e.g. ```python or ```).
    Raises ``ValueError`` with a descriptive message when no fence is found.
    """
    pattern = r"```(?:\w*)\n(.*?)```"
    match = re.search(pattern, response, re.DOTALL)
    if match is None:
        raise ValueError(
            "No markdown code fence found in the response. "
            "Expected a block delimited by ``` markers."
        )
    return match.group(1).rstrip("\n")


def format_code_block(code: str) -> str:
    """Wrap *code* in a markdown Python code fence."""
    return f"```python\n{code}\n```"


# ---------------------------------------------------------------------------
# Patch extraction helpers
# ---------------------------------------------------------------------------

_ROOT_CAUSE_HEADER = re.compile(
    r"(?:^|\n)#+\s*[Rr]oot\s+[Cc]ause.*?\n",
)
_DIFF_FENCE = re.compile(
    r"```(?:diff)?\n(---.*?```)",
    re.DOTALL,
)


def extract_patch(response: str) -> PatchData:
    """Extract root cause analysis and unified diff from an LLM response.

    Expected format (flexible):
      - A section headed ``## Root Cause`` (or similar) followed by prose.
      - A fenced code block containing a unified diff (starts with ``---``).

    Raises ``ValueError`` when the response cannot be parsed.
    """
    # --- unified diff -------------------------------------------------------
    diff_match = _DIFF_FENCE.search(response)
    if diff_match is None:
        raise ValueError(
            "No unified diff found in the response. "
            "Expected a fenced block starting with '---'."
        )
    unified_diff = diff_match.group(1)
    # Strip the trailing ``` that was captured as part of the group
    if unified_diff.endswith("```"):
        unified_diff = unified_diff[: -len("```")].rstrip("\n")

    # --- root cause ---------------------------------------------------------
    rc_match = _ROOT_CAUSE_HEADER.search(response)
    if rc_match is not None:
        # Text between the header and the diff fence (or end of string)
        start = rc_match.end()
        end = diff_match.start()
        root_cause = response[start:end].strip()
    else:
        # Fall back: everything before the diff fence
        root_cause = response[: diff_match.start()].strip()

    if not root_cause:
        root_cause = "(no root cause provided)"

    return PatchData(root_cause=root_cause, unified_diff=unified_diff)
