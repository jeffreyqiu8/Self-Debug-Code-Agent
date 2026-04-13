"""Data models for the self-debugging AI code agent."""

import json
from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import datetime


@dataclass
class TaskInput:
    task: str
    tests: Optional[str] = None


@dataclass
class OrchestratorConfig:
    max_iterations: int = 5
    timeout: int = 30
    sandbox_type: str = "subprocess"  # "subprocess" or "docker"
    llm_model: str = "gpt-4"
    llm_api_key: str = ""
    llm_base_url: Optional[str] = None


@dataclass
class GenerationResult:
    code: str
    raw_response: str
    metadata: dict = field(default_factory=dict)


@dataclass
class ExecutionResult:
    stdout: str
    stderr: str
    exit_code: int
    exception_trace: Optional[str] = None
    timed_out: bool = False


@dataclass
class TestResult:
    status: str  # "pass" or "fail"
    tests_passed: int = 0
    tests_failed: int = 0
    failure_details: list[dict] = field(default_factory=list)
    raw_output: str = ""


@dataclass
class PatchData:
    root_cause: str
    unified_diff: str


@dataclass
class DiagnosisResult:
    root_cause: str
    patch_data: PatchData
    raw_response: str


@dataclass
class PatchResult:
    success: bool
    patched_code: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class IterationLog:
    iteration: int
    timestamp: str
    code_snapshot: str
    execution_result: ExecutionResult
    test_result: TestResult
    diagnosis: Optional[DiagnosisResult] = None
    patch_result: Optional[PatchResult] = None


@dataclass
class FinalResult:
    final_code: str
    iterations_used: int
    status: str  # "success" or "failed"
    logs: list[IterationLog] = field(default_factory=list)


@dataclass
class MemoryRecord:
    error_signature: str
    root_cause: str
    patch_diff: str
    task_description: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


def serialize(obj) -> str:
    """Serialize a dataclass instance to a JSON string."""
    return json.dumps(asdict(obj), indent=2)


def deserialize_memory_record(data: dict) -> MemoryRecord:
    """Construct a MemoryRecord from a dictionary."""
    return MemoryRecord(**data)
