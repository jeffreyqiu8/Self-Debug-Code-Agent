"""Unit tests for the Orchestrator class.

The ``openai`` package may not be installed in the test environment, so we
inject a fake module into ``sys.modules`` before importing anything that
transitively depends on it.
"""

import sys
import types
import unittest
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Fake openai module so imports don't blow up when the package is absent.
# ---------------------------------------------------------------------------
_fake_openai = types.ModuleType("openai")
_fake_openai.OpenAI = MagicMock()  # type: ignore[attr-defined]
_fake_openai.APIError = type("APIError", (Exception,), {})  # type: ignore[attr-defined]
sys.modules.setdefault("openai", _fake_openai)

# Now safe to import project modules.
from models import (
    FinalResult,
    GenerationResult,
    OrchestratorConfig,
    PatchData,
    PatchResult,
    DiagnosisResult,
    TaskInput,
    TestResult,
)
from orchestrator import Orchestrator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(**overrides) -> OrchestratorConfig:
    defaults = dict(
        max_iterations=3,
        timeout=10,
        sandbox_type="subprocess",
        llm_model="test-model",
        llm_api_key="test-key",
        llm_base_url=None,
    )
    defaults.update(overrides)
    return OrchestratorConfig(**defaults)


def _build_orchestrator(**config_overrides) -> Orchestrator:
    """Build an Orchestrator with all sub-components mocked out."""
    orch = Orchestrator(_make_config(**config_overrides))
    # Replace real components with mocks so no LLM / sandbox calls happen.
    orch.code_generator = MagicMock()
    orch.debugger = MagicMock()
    orch.test_runner = MagicMock()
    orch.patcher = MagicMock()
    orch.memory = MagicMock()
    return orch


def _pass_test_result() -> TestResult:
    return TestResult(status="pass", tests_passed=3, tests_failed=0, failure_details=[], raw_output="OK")


def _fail_test_result() -> TestResult:
    return TestResult(
        status="fail",
        tests_passed=1,
        tests_failed=2,
        failure_details=[{"error": "AssertionError"}],
        raw_output="FAILED",
    )


def _diagnosis_result() -> DiagnosisResult:
    return DiagnosisResult(
        root_cause="Off-by-one error",
        patch_data=PatchData(root_cause="Off-by-one error", unified_diff="--- a\n+++ b\n"),
        raw_response="raw",
    )


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class TestInputValidation(unittest.TestCase):
    """Requirement 1.3 – empty task raises ValueError."""

    def test_empty_task_raises(self):
        orch = _build_orchestrator()
        with self.assertRaises(ValueError):
            orch.run(TaskInput(task=""))

    def test_whitespace_task_raises(self):
        orch = _build_orchestrator()
        with self.assertRaises(ValueError):
            orch.run(TaskInput(task="   "))


class TestSuccessOnFirstIteration(unittest.TestCase):
    """Requirement 8.1 – stop on first pass."""

    def test_success_first_iteration(self):
        orch = _build_orchestrator()
        orch.code_generator.generate_code.return_value = GenerationResult(code="print('hi')", raw_response="r")
        orch.code_generator.generate_tests.return_value = GenerationResult(code="assert True", raw_response="r")
        orch.test_runner.run.return_value = _pass_test_result()

        result = orch.run(TaskInput(task="write hello world"))

        self.assertEqual(result.status, "success")
        self.assertEqual(result.iterations_used, 1)
        self.assertEqual(len(result.logs), 1)
        self.assertEqual(result.final_code, "print('hi')")


class TestFailAfterMaxIterations(unittest.TestCase):
    """Requirement 8.2 – stop after max_iterations."""

    def test_fail_after_max(self):
        orch = _build_orchestrator(max_iterations=2)
        orch.code_generator.generate_code.return_value = GenerationResult(code="x=1", raw_response="r")
        orch.code_generator.generate_tests.return_value = GenerationResult(code="assert False", raw_response="r")
        orch.test_runner.run.return_value = _fail_test_result()
        orch.debugger.diagnose.return_value = _diagnosis_result()
        orch.patcher.apply_patch.return_value = PatchResult(success=True, patched_code="x=2")
        orch.memory.retrieve_similar.return_value = []

        result = orch.run(TaskInput(task="do something"))

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.iterations_used, 2)
        self.assertEqual(len(result.logs), 2)


class TestSuccessOnSecondIteration(unittest.TestCase):
    """Requirement 8.5 – continue loop until pass."""

    def test_success_second_iteration(self):
        orch = _build_orchestrator(max_iterations=5)
        orch.code_generator.generate_code.return_value = GenerationResult(code="x=1", raw_response="r")
        orch.code_generator.generate_tests.return_value = GenerationResult(code="assert True", raw_response="r")
        orch.test_runner.run.side_effect = [_fail_test_result(), _pass_test_result()]
        orch.debugger.diagnose.return_value = _diagnosis_result()
        orch.patcher.apply_patch.return_value = PatchResult(success=True, patched_code="x=2")
        orch.memory.retrieve_similar.return_value = []

        result = orch.run(TaskInput(task="fix something"))

        self.assertEqual(result.status, "success")
        self.assertEqual(result.iterations_used, 2)
        self.assertEqual(len(result.logs), 2)
        # Memory store should have been called for the successful fix
        orch.memory.store.assert_called_once()


class TestUsesProvidedTests(unittest.TestCase):
    """Requirement 1.2 – use provided tests."""

    def test_user_provided_tests(self):
        orch = _build_orchestrator()
        orch.code_generator.generate_code.return_value = GenerationResult(code="x=1", raw_response="r")
        orch.test_runner.run.return_value = _pass_test_result()

        user_tests = "def test_it(): assert True"
        result = orch.run(TaskInput(task="do it", tests=user_tests))

        self.assertEqual(result.status, "success")
        orch.code_generator.generate_tests.assert_not_called()
        call_args = orch.test_runner.run.call_args
        self.assertEqual(call_args[0][1], user_tests)


class TestErrorHandling(unittest.TestCase):
    """Error handling: LLM errors, patch failures, memory errors."""

    def test_code_generation_failure(self):
        orch = _build_orchestrator()
        orch.code_generator.generate_code.side_effect = RuntimeError("LLM down")

        result = orch.run(TaskInput(task="do it"))
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.iterations_used, 0)

    def test_diagnosis_llm_error_continues_loop(self):
        orch = _build_orchestrator(max_iterations=2)
        orch.code_generator.generate_code.return_value = GenerationResult(code="x=1", raw_response="r")
        orch.code_generator.generate_tests.return_value = GenerationResult(code="assert False", raw_response="r")
        orch.test_runner.run.return_value = _fail_test_result()
        orch.debugger.diagnose.side_effect = RuntimeError("API error")
        orch.memory.retrieve_similar.return_value = []

        result = orch.run(TaskInput(task="do it"))
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.iterations_used, 2)
        self.assertEqual(len(result.logs), 2)

    def test_patch_failure_continues_loop(self):
        orch = _build_orchestrator(max_iterations=2)
        orch.code_generator.generate_code.return_value = GenerationResult(code="x=1", raw_response="r")
        orch.code_generator.generate_tests.return_value = GenerationResult(code="assert False", raw_response="r")
        orch.test_runner.run.return_value = _fail_test_result()
        orch.debugger.diagnose.return_value = _diagnosis_result()
        orch.patcher.apply_patch.return_value = PatchResult(success=False, error_message="mismatch")
        orch.memory.retrieve_similar.return_value = []

        result = orch.run(TaskInput(task="do it"))
        self.assertEqual(result.status, "failed")
        self.assertEqual(len(result.logs), 2)

    def test_memory_error_continues(self):
        orch = _build_orchestrator(max_iterations=1)
        orch.code_generator.generate_code.return_value = GenerationResult(code="x=1", raw_response="r")
        orch.code_generator.generate_tests.return_value = GenerationResult(code="assert False", raw_response="r")
        orch.test_runner.run.return_value = _fail_test_result()
        orch.memory.retrieve_similar.side_effect = Exception("disk full")
        orch.debugger.diagnose.return_value = _diagnosis_result()
        orch.patcher.apply_patch.return_value = PatchResult(success=True, patched_code="x=2")

        result = orch.run(TaskInput(task="do it"))
        self.assertEqual(result.status, "failed")

    def test_diagnosis_parse_error_continues(self):
        """ValueError from parser should not crash the loop."""
        orch = _build_orchestrator(max_iterations=2)
        orch.code_generator.generate_code.return_value = GenerationResult(code="x=1", raw_response="r")
        orch.code_generator.generate_tests.return_value = GenerationResult(code="assert False", raw_response="r")
        orch.test_runner.run.return_value = _fail_test_result()
        orch.debugger.diagnose.side_effect = ValueError("No code fence found")
        orch.memory.retrieve_similar.return_value = []

        result = orch.run(TaskInput(task="do it"))
        self.assertEqual(result.status, "failed")
        self.assertEqual(len(result.logs), 2)


class TestLogStructure(unittest.TestCase):
    """Requirements 9.1, 9.3, 10.1 – logs contain required fields."""

    def test_log_has_timestamp_and_fields(self):
        orch = _build_orchestrator(max_iterations=1)
        orch.code_generator.generate_code.return_value = GenerationResult(code="x=1", raw_response="r")
        orch.code_generator.generate_tests.return_value = GenerationResult(code="assert True", raw_response="r")
        orch.test_runner.run.return_value = _pass_test_result()

        result = orch.run(TaskInput(task="do it"))

        self.assertEqual(len(result.logs), 1)
        log = result.logs[0]
        self.assertEqual(log.iteration, 1)
        self.assertTrue(len(log.timestamp) > 0)
        self.assertIsNotNone(log.code_snapshot)
        self.assertIsNotNone(log.execution_result)
        self.assertIsNotNone(log.test_result)

    def test_logs_in_chronological_order(self):
        orch = _build_orchestrator(max_iterations=3)
        orch.code_generator.generate_code.return_value = GenerationResult(code="x=1", raw_response="r")
        orch.code_generator.generate_tests.return_value = GenerationResult(code="assert True", raw_response="r")
        orch.test_runner.run.side_effect = [
            _fail_test_result(),
            _fail_test_result(),
            _pass_test_result(),
        ]
        orch.debugger.diagnose.return_value = _diagnosis_result()
        orch.patcher.apply_patch.return_value = PatchResult(success=True, patched_code="x=2")
        orch.memory.retrieve_similar.return_value = []

        result = orch.run(TaskInput(task="do it"))

        self.assertEqual(len(result.logs), 3)
        for i, log in enumerate(result.logs):
            self.assertEqual(log.iteration, i + 1)


class TestFinalResultStructure(unittest.TestCase):
    """Requirement 10.1, 10.2 – FinalResult has correct fields."""

    def test_final_result_success(self):
        orch = _build_orchestrator()
        orch.code_generator.generate_code.return_value = GenerationResult(code="x=1", raw_response="r")
        orch.code_generator.generate_tests.return_value = GenerationResult(code="assert True", raw_response="r")
        orch.test_runner.run.return_value = _pass_test_result()

        result = orch.run(TaskInput(task="do it"))

        self.assertIsInstance(result, FinalResult)
        self.assertEqual(result.status, "success")
        self.assertIsInstance(result.iterations_used, int)
        self.assertIsInstance(result.logs, list)
        self.assertIsInstance(result.final_code, str)

    def test_final_result_failed(self):
        orch = _build_orchestrator(max_iterations=1)
        orch.code_generator.generate_code.return_value = GenerationResult(code="x=1", raw_response="r")
        orch.code_generator.generate_tests.return_value = GenerationResult(code="assert False", raw_response="r")
        orch.test_runner.run.return_value = _fail_test_result()
        orch.debugger.diagnose.return_value = _diagnosis_result()
        orch.patcher.apply_patch.return_value = PatchResult(success=True, patched_code="x=2")
        orch.memory.retrieve_similar.return_value = []

        result = orch.run(TaskInput(task="do it"))

        self.assertIsInstance(result, FinalResult)
        self.assertEqual(result.status, "failed")


if __name__ == "__main__":
    unittest.main()
