"""Central orchestrator controlling the generate → execute → test → diagnose → patch loop."""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone

from agents.code_generator import CodeGeneratorAgent
from agents.debugger import DebuggerAgent
from agents.llm_client import LLMClient
from memory.store import MemoryStore
from models import (
    ExecutionResult,
    FinalResult,
    IterationLog,
    MemoryRecord,
    OrchestratorConfig,
    TaskInput,
    TestResult,
)
from sandbox.executor import DockerSandbox, SubprocessSandbox
from sandbox.patcher import PatchGenerator
from tests.runner import TestRunner

logger = logging.getLogger(__name__)


class Orchestrator:
    """Manages the self-debugging code agent lifecycle.

    Accepts an :class:`OrchestratorConfig`, wires up all sub-components,
    and exposes :meth:`run` to execute the full pipeline for a given task.
    """

    def __init__(self, config: OrchestratorConfig) -> None:
        self.config = config

        # --- LLM client & agents ---
        llm_client = LLMClient(
            api_key=config.llm_api_key,
            base_url=config.llm_base_url,
            model=config.llm_model,
        )
        self.code_generator = CodeGeneratorAgent(llm_client)
        self.debugger = DebuggerAgent(llm_client)

        # --- Sandbox ---
        if config.sandbox_type == "docker":
            sandbox = DockerSandbox()
        else:
            sandbox = SubprocessSandbox()

        # --- Test runner & patcher ---
        self.test_runner = TestRunner(sandbox)
        self.patcher = PatchGenerator()

        # --- Memory ---
        self.memory = MemoryStore()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, task_input: TaskInput) -> FinalResult:
        """Execute the full generate → debug loop and return a :class:`FinalResult`."""

        # --- Input validation (halt immediately on bad input) ---
        if not task_input.task or not task_input.task.strip():
            raise ValueError("TaskInput.task must be a non-empty string.")

        # --- Step 1: Generate initial code ---
        self._log_stdout("[orchestrator] Generating initial code …")
        try:
            gen_result = self.code_generator.generate_code(task_input.task)
        except (RuntimeError, ValueError) as exc:
            self._log_stdout(f"[orchestrator] Code generation failed: {exc}")
            return FinalResult(
                final_code="",
                iterations_used=0,
                status="failed",
                logs=[],
            )
        code = gen_result.code

        # --- Step 2: Obtain tests ---
        if task_input.tests:
            tests = task_input.tests
            self._log_stdout("[orchestrator] Using user-provided tests.")
        else:
            self._log_stdout("[orchestrator] Generating tests …")
            try:
                test_gen = self.code_generator.generate_tests(task_input.task, code)
                tests = test_gen.code
            except (RuntimeError, ValueError) as exc:
                self._log_stdout(f"[orchestrator] Test generation failed: {exc}")
                return FinalResult(
                    final_code=code,
                    iterations_used=0,
                    status="failed",
                    logs=[],
                )

        # --- Step 3: Iteration loop ---
        logs: list[IterationLog] = []
        max_iter = self.config.max_iterations

        for iteration in range(1, max_iter + 1):
            self._log_stdout(
                f"\n{'='*60}\n"
                f"[orchestrator] Iteration {iteration}/{max_iter}\n"
                f"{'='*60}"
            )

            iter_log = self._execute_iteration(code, tests, iteration)
            logs.append(iter_log)

            # Print human-readable summary for this iteration
            self._log_iteration_summary(iter_log)

            if iter_log.test_result.status == "pass":
                # Store successful fix in memory (only if we actually patched).
                # The diagnosis that led to success lives in the *previous*
                # iteration's log (the one that produced the patch).
                if iteration > 1 and len(logs) >= 2:
                    prev_log = logs[-2]
                    self._store_successful_fix(task_input, prev_log)
                self._log_stdout(
                    f"\n[orchestrator] ✓ All tests passed at iteration {iteration}."
                )
                return FinalResult(
                    final_code=iter_log.code_snapshot,
                    iterations_used=iteration,
                    status="success",
                    logs=logs,
                )

            # Update code for next iteration if a patch was applied
            if (
                iter_log.patch_result is not None
                and iter_log.patch_result.success
                and iter_log.patch_result.patched_code is not None
            ):
                code = iter_log.patch_result.patched_code
            # Otherwise keep the same code for the next iteration

        # Exhausted all iterations
        self._log_stdout(
            f"\n[orchestrator] ✗ Max iterations ({max_iter}) reached without passing tests."
        )
        return FinalResult(
            final_code=code,
            iterations_used=max_iter,
            status="failed",
            logs=logs,
        )

    # ------------------------------------------------------------------
    # Single iteration
    # ------------------------------------------------------------------

    def _execute_iteration(
        self, code: str, tests: str, iteration: int
    ) -> IterationLog:
        """Run one execute → test → (diagnose → patch) cycle."""

        timestamp = datetime.now(timezone.utc).isoformat()

        # --- Run tests ---
        try:
            test_result = self.test_runner.run(
                code, tests, timeout=self.config.timeout
            )
        except Exception as exc:
            logger.warning("TestRunner error: %s", exc)
            self._log_stdout(f"[iteration {iteration}] TestRunner error: {exc}")
            test_result = TestResult(
                status="fail",
                tests_passed=0,
                tests_failed=0,
                failure_details=[{"error": f"TestRunner exception: {exc}"}],
                raw_output=str(exc),
            )

        # Build a minimal ExecutionResult to satisfy the log schema.
        # The TestRunner already ran the code inside the sandbox, so we
        # mirror the relevant bits from the TestResult.
        execution_result = ExecutionResult(
            stdout=test_result.raw_output,
            stderr="",
            exit_code=0 if test_result.status == "pass" else 1,
        )

        # --- If tests pass, we're done for this iteration ---
        if test_result.status == "pass":
            return IterationLog(
                iteration=iteration,
                timestamp=timestamp,
                code_snapshot=code,
                execution_result=execution_result,
                test_result=test_result,
            )

        # --- Diagnose ---
        diagnosis = None
        patch_result = None

        # Retrieve similar past failures (graceful degradation)
        past_fixes: list[MemoryRecord] = []
        try:
            error_sig = self._build_error_signature(test_result)
            past_fixes = self.memory.retrieve_similar(error_sig)
        except Exception as exc:
            logger.warning("MemoryStore retrieval error: %s", exc)
            self._log_stdout(
                f"[iteration {iteration}] Memory retrieval warning: {exc}"
            )

        try:
            diagnosis = self.debugger.diagnose(
                code=code,
                error_logs=test_result.raw_output,
                test_results=test_result,
                past_fixes=past_fixes,
            )
        except RuntimeError as exc:
            # LLM API error — log and stop this iteration
            logger.warning("LLM API error during diagnosis: %s", exc)
            self._log_stdout(
                f"[iteration {iteration}] Diagnosis LLM error: {exc}"
            )
            return IterationLog(
                iteration=iteration,
                timestamp=timestamp,
                code_snapshot=code,
                execution_result=execution_result,
                test_result=test_result,
            )
        except ValueError as exc:
            # Parse error — log and continue to next iteration
            logger.warning("Diagnosis parse error: %s", exc)
            self._log_stdout(
                f"[iteration {iteration}] Diagnosis parse error: {exc}"
            )
            return IterationLog(
                iteration=iteration,
                timestamp=timestamp,
                code_snapshot=code,
                execution_result=execution_result,
                test_result=test_result,
            )

        # --- Apply patch ---
        try:
            patch_result = self.patcher.apply_patch(
                code, diagnosis.patch_data.unified_diff
            )
            if not patch_result.success:
                self._log_stdout(
                    f"[iteration {iteration}] Patch failed: {patch_result.error_message}"
                )
        except Exception as exc:
            logger.warning("Patch application error: %s", exc)
            self._log_stdout(
                f"[iteration {iteration}] Patch error: {exc}"
            )
            from models import PatchResult as _PR
            patch_result = _PR(
                success=False,
                error_message=f"Patch exception: {exc}",
            )

        return IterationLog(
            iteration=iteration,
            timestamp=timestamp,
            code_snapshot=code,
            execution_result=execution_result,
            test_result=test_result,
            diagnosis=diagnosis,
            patch_result=patch_result,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_error_signature(test_result: TestResult) -> str:
        """Derive a short error signature from test failure details."""
        parts: list[str] = []
        for detail in test_result.failure_details:
            if isinstance(detail, dict):
                msg = detail.get("message", detail.get("error", ""))
                parts.append(str(msg)[:200])
        return "; ".join(parts) if parts else test_result.raw_output[:300]

    def _store_successful_fix(
        self, task_input: TaskInput, iter_log: IterationLog
    ) -> None:
        """Persist a successful fix to the memory store."""
        if iter_log.diagnosis is None:
            return
        try:
            record = MemoryRecord(
                error_signature=self._build_error_signature(iter_log.test_result),
                root_cause=iter_log.diagnosis.root_cause,
                patch_diff=iter_log.diagnosis.patch_data.unified_diff,
                task_description=task_input.task,
            )
            self.memory.store(record)
        except Exception as exc:
            logger.warning("MemoryStore write error: %s", exc)
            self._log_stdout(f"[orchestrator] Memory store warning: {exc}")

    def _log_iteration_summary(self, log: IterationLog) -> None:
        """Print a human-readable summary of one iteration to stdout."""
        status = log.test_result.status.upper()
        passed = log.test_result.tests_passed
        failed = log.test_result.tests_failed
        diag = ""
        if log.diagnosis:
            diag = f"  Root cause: {log.diagnosis.root_cause[:120]}"
        patch = ""
        if log.patch_result:
            if log.patch_result.success:
                patch = "  Patch: applied successfully"
            else:
                patch = f"  Patch: FAILED – {log.patch_result.error_message}"

        self._log_stdout(
            f"[iteration {log.iteration}] [{log.timestamp}] "
            f"Status: {status} | Passed: {passed} | Failed: {failed}"
        )
        if diag:
            self._log_stdout(diag)
        if patch:
            self._log_stdout(patch)

    @staticmethod
    def _log_stdout(message: str) -> None:
        """Write a human-readable log line to stdout."""
        print(message, flush=True)
