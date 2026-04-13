"""Debugger agent that diagnoses failures and produces patches via an LLM."""

from __future__ import annotations

from agents.llm_client import LLMClient
from agents.response_parser import extract_patch
from models import DiagnosisResult, MemoryRecord, TestResult


class DebuggerAgent:
    """Analyzes test failures and produces line-level patch instructions."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    def diagnose(
        self,
        code: str,
        error_logs: str,
        test_results: TestResult,
        past_fixes: list[MemoryRecord],
    ) -> DiagnosisResult:
        """Diagnose a failure and return a root cause analysis with a patch.

        The LLM receives the current code, error output, structured test
        results, and any relevant past fixes from memory.  It is instructed
        to reply with a ``## Root Cause`` section followed by a unified diff
        inside a fenced code block.

        Raises ``RuntimeError`` on LLM API errors and ``ValueError`` when
        the response cannot be parsed into a valid patch.
        """
        past_context = self._format_past_fixes(past_fixes)

        failure_summary = self._format_test_results(test_results)

        messages = [
            {
                "role": "system",
                "content": (
                    "You are an expert Python debugger. "
                    "Analyze the failing code, error logs, and test results. "
                    "Respond with:\n"
                    "1. A section headed '## Root Cause' explaining the bug.\n"
                    "2. A fenced code block containing a unified diff "
                    "(starting with '---') that fixes the issue.\n"
                    "Produce minimal, line-level changes — do NOT rewrite "
                    "the entire file."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"## Current Code\n```python\n{code}\n```\n\n"
                    f"## Error Logs\n```\n{error_logs}\n```\n\n"
                    f"## Test Results\n{failure_summary}\n"
                    f"{past_context}"
                ),
            },
        ]

        raw_response = self._llm.chat(messages)
        patch_data = extract_patch(raw_response)
        return DiagnosisResult(
            root_cause=patch_data.root_cause,
            patch_data=patch_data,
            raw_response=raw_response,
        )

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_test_results(test_results: TestResult) -> str:
        lines = [
            f"Status: {test_results.status}",
            f"Passed: {test_results.tests_passed}",
            f"Failed: {test_results.tests_failed}",
        ]
        for detail in test_results.failure_details:
            lines.append(f"- {detail}")
        return "\n".join(lines)

    @staticmethod
    def _format_past_fixes(past_fixes: list[MemoryRecord]) -> str:
        if not past_fixes:
            return ""
        sections: list[str] = ["\n## Similar Past Fixes"]
        for i, record in enumerate(past_fixes, 1):
            sections.append(
                f"### Fix {i}\n"
                f"Error: {record.error_signature}\n"
                f"Root cause: {record.root_cause}\n"
                f"Patch:\n```diff\n{record.patch_diff}\n```"
            )
        return "\n".join(sections)
