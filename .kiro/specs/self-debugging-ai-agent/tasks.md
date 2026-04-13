# Implementation Plan: Autonomous Self-Debugging AI Code Agent

## Overview

Build a CLI-driven autonomous self-debugging code agent in Python. The implementation follows a bottom-up approach: data models and utilities first, then individual components (sandbox, parser, patcher, memory, agents), then the orchestrator loop, and finally the CLI entry point. Each step wires into the previous, ensuring no orphaned code.

## Tasks

- [x] 1. Set up project structure, dependencies, and data models
  - [x] 1.1 Create project directory structure and `requirements.txt`
    - Create directories: `agents/`, `sandbox/`, `tests/`, `memory/`, `demo_tasks/`
    - Create `__init__.py` files for each package
    - Create `requirements.txt` with: `openai>=1.0.0`, `docker>=7.0.0`, `hypothesis>=6.100.0`, `pytest>=8.0.0`
    - _Requirements: 12.1_

  - [x] 1.2 Implement all data models in `models.py`
    - Define dataclasses: `TaskInput`, `OrchestratorConfig`, `GenerationResult`, `ExecutionResult`, `TestResult`, `PatchData`, `DiagnosisResult`, `PatchResult`, `IterationLog`, `FinalResult`, `MemoryRecord`
    - Implement `serialize()` and `deserialize_memory_record()` helper functions
    - _Requirements: 1.1, 10.1, 11.1_

  - [ ]* 1.3 Write property test for TaskInput parsing correctness
    - **Property 1: TaskInput parsing correctness**
    - Test that valid JSON with a "task" field produces a correct TaskInput, and invalid/malformed input produces descriptive errors
    - **Validates: Requirements 1.1, 1.3, 1.4**

  - [ ]* 1.4 Write property test for FinalResult serialization round-trip
    - **Property 7: FinalResult serialization round-trip**
    - Test that serializing a FinalResult to JSON and deserializing back produces an equivalent object with logs in chronological order
    - **Validates: Requirements 10.1, 10.3, 9.1**

- [x] 2. Implement LLM client and response parser
  - [x] 2.1 Implement LLM client in `agents/llm_client.py`
    - Create `LLMClient` class wrapping OpenAI Python SDK (`client.chat.completions.create()`)
    - Support configurable `api_key`, `base_url`, and `model`
    - Handle `openai.APIError` and subclasses with descriptive error messages
    - _Requirements: 2.1, 2.3, 6.2, 6.4_

  - [x] 2.2 Implement response parser in `agents/response_parser.py`
    - Implement `extract_code_block(response)` to parse markdown code fences
    - Implement `format_code_block(code)` to wrap code in markdown fences
    - Implement `extract_patch(response)` to extract root cause and unified diff
    - Return descriptive parse errors for unrecognizable responses
    - _Requirements: 14.1, 14.2, 14.3, 14.4_

  - [ ]* 2.3 Write property test for code block parse/format round-trip
    - **Property 10: Code block parse/format round-trip**
    - Test that formatting code into a markdown block and parsing it back produces the original code, and repeating the cycle is idempotent
    - **Validates: Requirements 14.1, 14.3**

  - [ ]* 2.4 Write property test for patch instruction extraction round-trip
    - **Property 11: Patch instruction extraction round-trip**
    - Test that formatting root cause + diff into an LLM response and extracting them back produces the originals
    - **Validates: Requirements 14.2**

  - [ ]* 2.5 Write property test for unrecognizable response rejection
    - **Property 12: Unrecognizable response rejection**
    - Test that strings without markdown code fences produce a descriptive parse error
    - **Validates: Requirements 14.4**

- [x] 3. Implement sandbox execution backends
  - [x] 3.1 Implement sandbox executor in `sandbox/executor.py`
    - Define `SandboxExecutor` protocol with `execute(code, timeout)` method
    - Implement `SubprocessSandbox` using `subprocess.run()` with restricted permissions
    - Implement `DockerSandbox` using `docker` Python SDK
    - Capture stdout, stderr, exception traces; handle timeouts with `timed_out` flag
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ]* 3.2 Write property test for sandbox output capture
    - **Property 2: Sandbox output capture**
    - Test that code producing stdout/stderr/exceptions returns correct ExecutionResult fields and exit codes
    - **Validates: Requirements 4.2, 4.3**

- [x] 4. Implement patch generator
  - [x] 4.1 Implement patch generator in `sandbox/patcher.py`
    - Create `PatchGenerator` class with `apply_patch(original_code, unified_diff)` and `generate_diff(original, modified)` methods
    - Use `difflib` for generating unified diffs
    - Return `PatchResult` with `success=False` and descriptive error for failed patches
    - Preserve all unchanged lines when applying patches
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [ ]* 4.2 Write property test for patch application round-trip
    - **Property 4: Patch application round-trip**
    - Test that generating a diff from A to B and applying it to A produces B
    - **Validates: Requirements 7.1, 7.2, 7.4**

  - [ ]* 4.3 Write property test for invalid patch detection
    - **Property 5: Invalid patch detection**
    - Test that applying a mismatched diff returns PatchResult with `success=False` and non-empty `error_message`
    - **Validates: Requirements 7.3**

- [x] 5. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement test runner
  - [x] 6.1 Implement test runner in `tests/runner.py`
    - Create `TestRunner` class that combines code + tests into a single script
    - Execute combined script in sandbox and parse output into `TestResult`
    - Parse pass/fail counts, failure details, and overall status
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [ ]* 6.2 Write property test for test result parsing
    - **Property 3: Test result parsing**
    - Test that output with N tests, P passes, F failures produces correct TestResult fields
    - **Validates: Requirements 5.2, 5.3, 5.4**

- [x] 7. Implement memory store
  - [x] 7.1 Implement memory store in `memory/store.py`
    - Create `MemoryStore` class with `store(record)`, `retrieve_similar(error_signature, top_k)`, `_load()`, `_save()` methods
    - Persist records to JSON file on disk
    - Create empty JSON file if it does not exist on startup
    - Retrieve similar records using substring matching on `error_signature`
    - _Requirements: 11.1, 11.2, 11.3, 11.4_

  - [ ]* 7.2 Write property test for MemoryRecord persistence round-trip
    - **Property 8: MemoryRecord persistence round-trip**
    - Test that storing a MemoryRecord and loading all records includes an equivalent record, and the JSON file is valid after each write
    - **Validates: Requirements 11.1, 11.3**

  - [ ]* 7.3 Write property test for memory retrieval by error signature
    - **Property 9: Memory retrieval by error signature**
    - Test that retrieval returns only records whose `error_signature` contains the query substring
    - **Validates: Requirements 11.2**

- [x] 8. Implement code generator and debugger agents
  - [x] 8.1 Implement code generator agent in `agents/code_generator.py`
    - Create `CodeGeneratorAgent` class with `generate_code(task_description)` and `generate_tests(task_description, code)` methods
    - Use `LLMClient` for API calls and `response_parser` for extracting code
    - Return `GenerationResult` with code string and metadata
    - Generate minimum 3 test cases covering normal, edge, and error scenarios when auto-generating tests
    - _Requirements: 2.1, 2.2, 2.4, 3.1, 3.2, 3.3_

  - [x] 8.2 Implement debugger agent in `agents/debugger.py`
    - Create `DebuggerAgent` class with `diagnose(code, error_logs, test_results, past_fixes)` method
    - Send failure context to LLM and extract root cause + unified diff patch
    - Return `DiagnosisResult` with root cause, patch data, and raw response
    - Produce line-level patch instructions, not full rewrites
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [x] 9. Implement orchestrator loop
  - [x] 9.1 Implement orchestrator in `orchestrator.py`
    - Create `Orchestrator` class with `run(task_input)` and `_execute_iteration(code, tests, iteration)` methods
    - Implement generate → execute → test → diagnose → patch loop
    - Stop on success (all tests pass) or when max_iterations reached
    - Log iteration number, code snapshot, execution result, test result, diagnosis, and timestamp for each iteration
    - Store successful fixes in MemoryStore; retrieve similar past failures for diagnosis context
    - Handle errors gracefully: fail-forward for sandbox/patch/parse errors, halt on input validation errors
    - Return structured `FinalResult` with final_code, iterations_used, status, and logs
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 9.1, 9.2, 9.3, 9.4, 10.1, 10.2, 10.3_

  - [ ]* 9.2 Write property test for orchestrator loop termination
    - **Property 6: Orchestrator loop termination**
    - Test that the loop executes at most N iterations, stops early on success, and returns correct status
    - Use mock sandbox/agents to control test outcomes per iteration
    - **Validates: Requirements 8.1, 8.2, 8.3, 8.5**

- [x] 10. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Implement CLI entry point and demo tasks
  - [x] 11.1 Implement CLI entry point in `main.py`
    - Use `argparse` to parse `--task`, `--tests`, `--max-iterations` arguments
    - Run preconfigured demo tasks when no arguments provided
    - Build `OrchestratorConfig` and `TaskInput` from CLI args
    - Invoke `Orchestrator.run()` and print JSON result to stdout
    - _Requirements: 12.2, 13.1, 13.2, 13.3, 13.4_

  - [x] 11.2 Create demo task files
    - Create `demo_tasks/task1.json` with a simple function task (e.g., fibonacci)
    - Create `demo_tasks/task2.json` with a data structure task (e.g., stack implementation)
    - Ensure both are valid JSON with "task" field
    - _Requirements: 12.3_

  - [ ]* 11.3 Write unit tests for CLI argument parsing
    - Test `--task`, `--tests`, `--max-iterations` argument parsing
    - Test default behavior with no arguments
    - Test error handling for invalid arguments
    - _Requirements: 13.1, 13.2, 13.3, 13.4_

- [ ] 12. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- All code is Python; uses `openai`, `docker`, `hypothesis`, and `pytest` libraries
