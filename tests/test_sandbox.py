"""Unit tests for sandbox execution backends."""

import pytest
from sandbox.executor import SubprocessSandbox, DockerSandbox, SandboxExecutor, _extract_traceback
from models import ExecutionResult


class TestSubprocessSandbox:
    """Tests for SubprocessSandbox."""

    def setup_method(self):
        self.sandbox = SubprocessSandbox()

    def test_conforms_to_protocol(self):
        """SubprocessSandbox should satisfy the SandboxExecutor protocol."""
        assert isinstance(self.sandbox, SandboxExecutor)

    def test_captures_stdout(self):
        """Should capture stdout from executed code."""
        result = self.sandbox.execute("print('hello world')")
        assert result.stdout.strip() == "hello world"
        assert result.exit_code == 0
        assert result.timed_out is False

    def test_captures_stderr(self):
        """Should capture stderr from executed code."""
        result = self.sandbox.execute("import sys; sys.stderr.write('error msg')")
        assert "error msg" in result.stderr
        assert result.exit_code == 0

    def test_captures_exception_trace(self):
        """Should capture exception traceback for failing code."""
        result = self.sandbox.execute("raise ValueError('test error')")
        assert result.exit_code != 0
        assert result.exception_trace is not None
        assert "ValueError" in result.exception_trace
        assert "test error" in result.exception_trace

    def test_handles_timeout(self):
        """Should terminate and flag timed_out for long-running code."""
        result = self.sandbox.execute("import time; time.sleep(60)", timeout=1)
        assert result.timed_out is True
        assert result.exit_code == -1
        assert "TimeoutError" in (result.exception_trace or "")

    def test_successful_execution_returns_zero_exit_code(self):
        """Successful code should return exit_code 0."""
        result = self.sandbox.execute("x = 1 + 1")
        assert result.exit_code == 0
        assert result.timed_out is False
        assert result.exception_trace is None

    def test_returns_execution_result_type(self):
        """Should always return an ExecutionResult instance."""
        result = self.sandbox.execute("print('test')")
        assert isinstance(result, ExecutionResult)

    def test_syntax_error_captured(self):
        """Syntax errors should be captured in stderr/exception_trace."""
        result = self.sandbox.execute("def foo(:")
        assert result.exit_code != 0
        assert result.stderr != ""


class TestDockerSandbox:
    """Tests for DockerSandbox protocol conformance (no Docker required)."""

    def test_conforms_to_protocol(self):
        """DockerSandbox should satisfy the SandboxExecutor protocol."""
        sandbox = DockerSandbox()
        assert isinstance(sandbox, SandboxExecutor)

    def test_default_image(self):
        """Should default to python:3.12-slim image."""
        sandbox = DockerSandbox()
        assert sandbox.image == "python:3.12-slim"

    def test_custom_image(self):
        """Should accept a custom image."""
        sandbox = DockerSandbox(image="python:3.11")
        assert sandbox.image == "python:3.11"


class TestExtractTraceback:
    """Tests for the _extract_traceback helper."""

    def test_extracts_traceback_from_stderr(self):
        stderr = "Some warning\nTraceback (most recent call last):\n  File ...\nValueError: bad"
        result = _extract_traceback(stderr)
        assert result is not None
        assert result.startswith("Traceback")
        assert "ValueError" in result

    def test_returns_full_stderr_when_no_traceback_marker(self):
        stderr = "some error without traceback"
        result = _extract_traceback(stderr)
        assert result == "some error without traceback"

    def test_returns_none_for_empty_string(self):
        assert _extract_traceback("") is None

    def test_returns_none_for_none_like_empty(self):
        assert _extract_traceback("") is None
