"""Test runner that executes tests against generated code in a sandbox."""

import re
from typing import Optional

from models import TestResult
from sandbox.executor import SandboxExecutor


# Template appended to the combined script to run unittest and produce
# machine-parseable output.  We use unittest's TextTestRunner so the
# output format is predictable regardless of whether the user wrote
# unittest-style or pytest-style tests (pytest can also be discovered
# by unittest when written as functions, but we normalise on unittest
# here for reliable parsing).
_RUNNER_SNIPPET = """

# --- auto-appended test runner ---
import unittest as __unittest
import sys as __sys

if __name__ == "__main__":
    loader = __unittest.TestLoader()
    suite = loader.loadTestsFromModule(__sys.modules[__name__])
    runner = __unittest.TextTestRunner(verbosity=2, stream=__sys.stderr)
    result = runner.run(suite)
    # Print a machine-readable summary line to stdout
    print(f"__TEST_SUMMARY__:ran={result.testsRun},failures={len(result.failures)},errors={len(result.errors)}")
    __sys.exit(0 if result.wasSuccessful() else 1)
"""


class TestRunner:
    """Execute tests within a sandbox and parse results into TestResult."""

    def __init__(self, sandbox: SandboxExecutor) -> None:
        self.sandbox = sandbox

    def run(self, code: str, test_code: str, timeout: int = 30) -> TestResult:
        """Combine code + tests into a single script, execute in sandbox,
        parse output into TestResult.
        """
        combined = self._combine(code, test_code)
        execution = self.sandbox.execute(combined, timeout=timeout)

        if execution.timed_out:
            return TestResult(
                status="fail",
                tests_passed=0,
                tests_failed=0,
                failure_details=[{"error": "Execution timed out"}],
                raw_output=execution.stdout + execution.stderr,
            )

        return self._parse_output(execution.stdout, execution.stderr, execution.exit_code)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _combine(code: str, test_code: str) -> str:
        """Merge user code and test code into a single runnable script."""
        parts = [code.rstrip(), "", test_code.rstrip(), _RUNNER_SNIPPET]
        return "\n".join(parts)

    @staticmethod
    def _parse_output(stdout: str, stderr: str, exit_code: int) -> TestResult:
        """Parse unittest verbose output into a TestResult."""
        raw_output = stdout + stderr

        # 1. Try the machine-readable summary line we injected.
        summary = _parse_summary_line(stdout)
        if summary is not None:
            ran, failures_count, errors_count = summary
            total_failed = failures_count + errors_count
            total_passed = max(ran - total_failed, 0)
            failure_details = _extract_failure_details(stderr)
            status = "pass" if total_failed == 0 else "fail"
            return TestResult(
                status=status,
                tests_passed=total_passed,
                tests_failed=total_failed,
                failure_details=failure_details,
                raw_output=raw_output,
            )

        # 2. Fallback: parse the standard unittest summary from stderr
        #    e.g. "Ran 5 tests in 0.001s" followed by "OK" or "FAILED (...)"
        ran_match = re.search(r"Ran (\d+) test", stderr)
        if ran_match:
            ran = int(ran_match.group(1))
            failures_count = 0
            errors_count = 0
            fail_match = re.search(
                r"FAILED \((?:failures=(\d+))?(?:,\s*)?(?:errors=(\d+))?\)", stderr
            )
            if fail_match:
                failures_count = int(fail_match.group(1) or 0)
                errors_count = int(fail_match.group(2) or 0)
            total_failed = failures_count + errors_count
            total_passed = max(ran - total_failed, 0)
            failure_details = _extract_failure_details(stderr)
            status = "pass" if total_failed == 0 else "fail"
            return TestResult(
                status=status,
                tests_passed=total_passed,
                tests_failed=total_failed,
                failure_details=failure_details,
                raw_output=raw_output,
            )

        # 3. Could not parse – treat as failure if exit_code != 0
        if exit_code != 0:
            return TestResult(
                status="fail",
                tests_passed=0,
                tests_failed=0,
                failure_details=[{"error": stderr.strip() or "Unknown error"}],
                raw_output=raw_output,
            )

        # 4. exit_code 0 but no recognisable test output – assume pass
        return TestResult(
            status="pass",
            tests_passed=0,
            tests_failed=0,
            failure_details=[],
            raw_output=raw_output,
        )


# ------------------------------------------------------------------
# Module-level parsing helpers
# ------------------------------------------------------------------

_SUMMARY_RE = re.compile(
    r"__TEST_SUMMARY__:ran=(\d+),failures=(\d+),errors=(\d+)"
)


def _parse_summary_line(stdout: str) -> Optional[tuple[int, int, int]]:
    """Return (ran, failures, errors) from the injected summary line, or None."""
    m = _SUMMARY_RE.search(stdout)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    return None


def _extract_failure_details(stderr: str) -> list[dict]:
    """Extract individual failure/error blocks from unittest verbose output.

    unittest separates failure blocks with lines of '=' characters.
    Each block starts with FAIL: or ERROR: and contains a traceback.
    """
    details: list[dict] = []
    # Split on separator lines (70 '=' chars is the unittest default)
    blocks = re.split(r"={50,}", stderr)
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        # Look for FAIL: or ERROR: header
        header_match = re.match(r"(FAIL|ERROR):\s*(.+)", block)
        if header_match:
            kind = header_match.group(1)
            test_name = header_match.group(2).strip()
            # The traceback follows after a line of '-' chars
            tb_parts = re.split(r"-{50,}", block, maxsplit=1)
            traceback_text = tb_parts[1].strip() if len(tb_parts) > 1 else ""
            details.append({
                "test": test_name,
                "type": kind.lower(),
                "message": traceback_text,
            })
    return details
