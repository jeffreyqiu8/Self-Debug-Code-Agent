"""Unit tests for the TestRunner class."""

import pytest
from tests.runner import TestRunner, _parse_summary_line, _extract_failure_details
from sandbox.executor import SubprocessSandbox
from models import TestResult


class TestTestRunnerIntegration:
    """Integration tests that run real code + tests in the subprocess sandbox."""

    def setup_method(self):
        self.sandbox = SubprocessSandbox()
        self.runner = TestRunner(self.sandbox)

    def test_all_tests_pass(self):
        """When all tests pass, status should be 'pass'."""
        code = "def add(a, b):\n    return a + b\n"
        test_code = (
            "import unittest\n"
            "class TestAdd(unittest.TestCase):\n"
            "    def test_basic(self):\n"
            "        self.assertEqual(add(1, 2), 3)\n"
            "    def test_zero(self):\n"
            "        self.assertEqual(add(0, 0), 0)\n"
        )
        result = self.runner.run(code, test_code)
        assert isinstance(result, TestResult)
        assert result.status == "pass"
        assert result.tests_passed == 2
        assert result.tests_failed == 0
        assert result.failure_details == []

    def test_some_tests_fail(self):
        """When some tests fail, status should be 'fail' with failure details."""
        code = "def add(a, b):\n    return a - b  # bug!\n"
        test_code = (
            "import unittest\n"
            "class TestAdd(unittest.TestCase):\n"
            "    def test_basic(self):\n"
            "        self.assertEqual(add(1, 2), 3)\n"
            "    def test_zero(self):\n"
            "        self.assertEqual(add(0, 0), 0)\n"
        )
        result = self.runner.run(code, test_code)
        assert result.status == "fail"
        assert result.tests_failed >= 1
        assert result.tests_passed + result.tests_failed == 2
        assert len(result.failure_details) >= 1

    def test_all_tests_fail(self):
        """When all tests fail, status should be 'fail'."""
        code = "def greet(name):\n    return 'bye'\n"
        test_code = (
            "import unittest\n"
            "class TestGreet(unittest.TestCase):\n"
            "    def test_hello(self):\n"
            "        self.assertEqual(greet('world'), 'hello world')\n"
            "    def test_empty(self):\n"
            "        self.assertEqual(greet(''), 'hello ')\n"
        )
        result = self.runner.run(code, test_code)
        assert result.status == "fail"
        assert result.tests_failed == 2
        assert result.tests_passed == 0

    def test_code_with_error_produces_fail(self):
        """Code that raises an error during test should produce 'fail'."""
        code = "def divide(a, b):\n    return a / b\n"
        test_code = (
            "import unittest\n"
            "class TestDivide(unittest.TestCase):\n"
            "    def test_divide_by_zero(self):\n"
            "        self.assertEqual(divide(1, 0), 0)\n"
            "    def test_normal(self):\n"
            "        self.assertEqual(divide(4, 2), 2.0)\n"
        )
        result = self.runner.run(code, test_code)
        assert result.status == "fail"
        assert result.tests_failed >= 1

    def test_raw_output_populated(self):
        """raw_output should contain the combined stdout+stderr."""
        code = "def noop():\n    pass\n"
        test_code = (
            "import unittest\n"
            "class TestNoop(unittest.TestCase):\n"
            "    def test_it(self):\n"
            "        noop()\n"
        )
        result = self.runner.run(code, test_code)
        assert result.raw_output != ""


class TestParseSummaryLine:
    """Tests for the _parse_summary_line helper."""

    def test_valid_summary(self):
        line = "some output\n__TEST_SUMMARY__:ran=5,failures=1,errors=0\n"
        assert _parse_summary_line(line) == (5, 1, 0)

    def test_no_summary(self):
        assert _parse_summary_line("just some text") is None

    def test_summary_with_errors(self):
        line = "__TEST_SUMMARY__:ran=3,failures=0,errors=2"
        assert _parse_summary_line(line) == (3, 0, 2)


class TestExtractFailureDetails:
    """Tests for the _extract_failure_details helper."""

    def test_no_failures(self):
        assert _extract_failure_details("Ran 2 tests in 0.001s\n\nOK\n") == []

    def test_single_failure(self):
        stderr = (
            "test_basic (__main__.TestAdd.test_basic) ... FAIL\n"
            "======================================================================\n"
            "FAIL: test_basic (__main__.TestAdd.test_basic)\n"
            "----------------------------------------------------------------------\n"
            "Traceback (most recent call last):\n"
            '  File "test.py", line 5, in test_basic\n'
            "    self.assertEqual(1, 2)\n"
            "AssertionError: 1 != 2\n"
            "----------------------------------------------------------------------\n"
            "Ran 1 test in 0.001s\n\n"
            "FAILED (failures=1)\n"
        )
        details = _extract_failure_details(stderr)
        assert len(details) == 1
        assert details[0]["type"] == "fail"
        assert "test_basic" in details[0]["test"]
