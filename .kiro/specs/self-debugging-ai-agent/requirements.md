# Requirements Document

## Introduction

The Autonomous Self-Debugging AI Code Agent is a multi-agent AI system that accepts programming tasks from users, generates Python code solutions, executes the code in a sandboxed environment, detects failures, diagnoses root causes using an LLM, applies incremental patches, and repeats the cycle until tests pass or a maximum iteration limit is reached. The system demonstrates an autonomous self-healing code loop with clear logging of each reasoning-execution-failure-fix cycle.

## Glossary

- **Orchestrator**: The central controller loop that manages the generate → execute → evaluate → debug → patch → repeat lifecycle for a given programming task.
- **Code_Generator_Agent**: An LLM-powered agent that produces an initial Python code solution from a user-provided task description.
- **Sandbox**: An isolated execution environment (Docker container or restricted subprocess) that runs generated Python code safely and captures output.
- **Test_Runner**: A component that executes unit tests against generated code and produces structured pass/fail results with failure logs.
- **Debugger_Agent**: An LLM-powered agent that analyzes failing code, error logs, and test results to produce a root cause analysis and patch instructions.
- **Patch_Generator**: A component that converts debugger output into a unified diff and applies the patch to existing code incrementally without full rewrites.
- **Memory_Store**: A persistent JSON-based store that records past failures and fixes for retrieval during future debugging sessions.
- **Iteration**: A single cycle through the execute → evaluate → debug → patch pipeline within the Orchestrator loop.
- **Task_Input**: A JSON object containing a "task" field with the programming problem description and an optional "tests" field with unit test code.
- **Execution_Result**: A structured object containing stdout, stderr, exception traces, and exit code from a Sandbox run.
- **Max_Iterations**: The configurable upper bound (default 5–10) on the number of debug-patch iterations the Orchestrator performs before stopping.

## Requirements

### Requirement 1: Accept Programming Task Input

**User Story:** As a user, I want to submit a programming task with optional tests via the CLI, so that the system can begin generating a solution.

#### Acceptance Criteria

1. WHEN a Task_Input JSON object containing a "task" field is provided, THE Orchestrator SHALL parse the input and initiate the code generation pipeline.
2. WHEN a Task_Input JSON object contains a "tests" field, THE Orchestrator SHALL use the provided tests for validation instead of generating tests.
3. IF a Task_Input JSON object is missing the "task" field, THEN THE Orchestrator SHALL return a descriptive error message indicating the required field.
4. IF a Task_Input JSON object contains malformed JSON, THEN THE Orchestrator SHALL return a descriptive parse error message and halt execution.

### Requirement 2: Generate Initial Code Solution

**User Story:** As a user, I want the system to generate a Python code solution from my task description, so that I have an initial implementation to work with.

#### Acceptance Criteria

1. WHEN a valid task description is received, THE Code_Generator_Agent SHALL send the task description to an OpenAI-compatible chat API and return a single-module Python code string.
2. THE Code_Generator_Agent SHALL produce code that is syntactically valid Python.
3. IF the OpenAI-compatible chat API returns an error, THEN THE Code_Generator_Agent SHALL propagate a descriptive error message to the Orchestrator.
4. THE Code_Generator_Agent SHALL include the generated code in a structured response object containing the code string and any metadata from the LLM response.

### Requirement 3: Generate Unit Tests When Not Provided

**User Story:** As a user, I want the system to auto-generate unit tests when I do not provide them, so that the solution can still be validated automatically.

#### Acceptance Criteria

1. WHEN the Task_Input does not contain a "tests" field, THE Code_Generator_Agent SHALL generate Python unit tests for the given task description.
2. THE Code_Generator_Agent SHALL produce unit tests that use the Python `unittest` or `pytest` framework.
3. THE Code_Generator_Agent SHALL generate a minimum of 3 test cases covering normal, edge, and error scenarios.

### Requirement 4: Execute Code in Sandbox

**User Story:** As a user, I want generated code to run in an isolated sandbox, so that execution is safe and does not affect the host system.

#### Acceptance Criteria

1. WHEN the Orchestrator provides code for execution, THE Sandbox SHALL execute the code in an isolated environment using Docker or a restricted subprocess.
2. THE Sandbox SHALL capture stdout, stderr, and exception traces from the executed code.
3. THE Sandbox SHALL return a structured Execution_Result containing stdout, stderr, exception traces, and exit code.
4. IF code execution exceeds a configurable timeout (default 30 seconds), THEN THE Sandbox SHALL terminate the execution and return a timeout error in the Execution_Result.
5. THE Sandbox SHALL prevent the executed code from accessing the host filesystem, network (except localhost), or system processes outside the sandbox boundary.

### Requirement 5: Run Tests and Report Results

**User Story:** As a user, I want the system to run unit tests against the generated code, so that I can know whether the solution is correct.

#### Acceptance Criteria

1. WHEN the Sandbox completes code execution without a timeout, THE Test_Runner SHALL execute the unit tests against the generated code within the Sandbox.
2. THE Test_Runner SHALL return a structured result containing: overall pass/fail status, number of tests passed, number of tests failed, and failure log details for each failing test.
3. WHEN all tests pass, THE Test_Runner SHALL set the overall status to "pass".
4. WHEN one or more tests fail, THE Test_Runner SHALL set the overall status to "fail" and include the failure messages and stack traces.

### Requirement 6: Diagnose Failures Using Debugger Agent

**User Story:** As a user, I want the system to automatically diagnose why tests failed, so that the code can be fixed without manual intervention.

#### Acceptance Criteria

1. WHEN the Test_Runner reports a "fail" status, THE Debugger_Agent SHALL receive the current code, error logs, and failing test details.
2. THE Debugger_Agent SHALL send the failure context to an OpenAI-compatible chat API and return a root cause analysis and patch instructions.
3. THE Debugger_Agent SHALL produce patch instructions that describe specific line-level changes rather than full code rewrites.
4. IF the OpenAI-compatible chat API returns an error, THEN THE Debugger_Agent SHALL propagate a descriptive error message to the Orchestrator.

### Requirement 7: Apply Incremental Patches

**User Story:** As a user, I want the system to apply fixes incrementally as patches, so that each iteration builds on the previous code rather than rewriting it entirely.

#### Acceptance Criteria

1. WHEN the Debugger_Agent produces patch instructions, THE Patch_Generator SHALL convert the instructions into a unified diff format.
2. THE Patch_Generator SHALL apply the unified diff to the existing code, producing an updated code version.
3. IF the unified diff fails to apply cleanly, THEN THE Patch_Generator SHALL report the failure to the Orchestrator with a descriptive error message.
4. THE Patch_Generator SHALL preserve all unchanged lines of the original code when applying a patch.

### Requirement 8: Control Iteration Loop

**User Story:** As a user, I want the system to automatically retry fixing code up to a maximum number of iterations, so that it has multiple chances to produce a correct solution.

#### Acceptance Criteria

1. WHEN all tests pass after an iteration, THE Orchestrator SHALL stop the loop and return a success result.
2. WHEN the iteration count reaches Max_Iterations, THE Orchestrator SHALL stop the loop and return a failure result with the last code version and all iteration logs.
3. THE Orchestrator SHALL increment the iteration counter by 1 after each debug-patch cycle.
4. THE Orchestrator SHALL use a configurable Max_Iterations value with a default of 5.
5. WHILE the iteration count is less than Max_Iterations and tests have not passed, THE Orchestrator SHALL continue the debug → patch → execute → test cycle.

### Requirement 9: Log Every Iteration

**User Story:** As a user, I want clear logs of each iteration showing reasoning, execution, failure, and fix details, so that I can understand the system's self-correction behavior.

#### Acceptance Criteria

1. THE Orchestrator SHALL log the iteration number, generated or patched code, Execution_Result, Test_Runner result, and Debugger_Agent analysis for each iteration.
2. THE Orchestrator SHALL write logs to stdout in a human-readable format.
3. THE Orchestrator SHALL include a timestamp for each log entry.
4. WHEN the loop completes, THE Orchestrator SHALL output a summary containing: final status (success or failed), total iterations used, and the final code version.

### Requirement 10: Produce Structured Final Output

**User Story:** As a user, I want the system to return a structured JSON output at the end, so that I can programmatically consume the results.

#### Acceptance Criteria

1. WHEN the Orchestrator loop completes, THE Orchestrator SHALL return a JSON object containing: "final_code" (string), "iterations_used" (integer), "status" ("success" or "failed"), and "logs" (array of iteration log objects).
2. THE Orchestrator SHALL set "status" to "success" when all tests pass and "failed" when Max_Iterations is reached without all tests passing.
3. THE Orchestrator SHALL include all iteration logs in the "logs" array in chronological order.

### Requirement 11: Store Past Failures and Fixes in Memory

**User Story:** As a user, I want the system to remember past failures and fixes, so that it can improve debugging by referencing similar past errors.

#### Acceptance Criteria

1. WHEN the Debugger_Agent produces a successful fix that leads to passing tests, THE Memory_Store SHALL persist the error signature, root cause analysis, and applied patch as a JSON record.
2. WHEN the Debugger_Agent begins diagnosing a failure, THE Memory_Store SHALL retrieve past records with similar error signatures and provide them as additional context to the Debugger_Agent.
3. THE Memory_Store SHALL persist records to a JSON file on disk so that memory survives across sessions.
4. IF the Memory_Store JSON file does not exist on startup, THEN THE Memory_Store SHALL create an empty JSON file.

### Requirement 12: Provide Modular Project Structure

**User Story:** As a developer, I want the codebase to be organized into clear, modular files, so that the system is easy to understand and extend.

#### Acceptance Criteria

1. THE system SHALL organize source code into the following modules: `main.py` (entry point), `orchestrator.py`, `agents/` (containing Code_Generator_Agent and Debugger_Agent), `sandbox/` (containing Sandbox execution logic), `tests/` (containing Test_Runner logic), and `memory/` (containing Memory_Store logic).
2. THE system SHALL provide a `main.py` entry point that accepts a Task_Input and invokes the Orchestrator.
3. THE system SHALL include at least 2 preconfigured demo tasks that can be run via `python main.py`.

### Requirement 13: Support CLI Execution

**User Story:** As a user, I want to run the system from the command line, so that I can use it without a frontend.

#### Acceptance Criteria

1. WHEN the user runs `python main.py` without arguments, THE system SHALL execute the preconfigured demo tasks sequentially and print results to stdout.
2. WHEN the user provides a `--task` argument with a task description, THE system SHALL use the provided task description instead of the demo tasks.
3. WHEN the user provides a `--tests` argument with a file path, THE system SHALL read the test code from the specified file and use it for validation.
4. WHEN the user provides a `--max-iterations` argument with an integer value, THE system SHALL use the provided value as Max_Iterations.

### Requirement 14: Parse and Format LLM Responses

**User Story:** As a developer, I want LLM responses to be reliably parsed into structured code and patch data, so that the system can process them programmatically.

#### Acceptance Criteria

1. WHEN the Code_Generator_Agent receives an LLM response containing a code block, THE Code_Generator_Agent SHALL extract the Python code from the response by parsing markdown code fences.
2. WHEN the Debugger_Agent receives an LLM response containing patch instructions, THE Debugger_Agent SHALL extract the root cause analysis text and the unified diff from the response.
3. FOR ALL valid LLM responses containing code blocks, parsing the response and then formatting the extracted code back into a code block SHALL produce content that re-parses to an equivalent code string (round-trip property).
4. IF an LLM response does not contain a recognizable code block or patch format, THEN THE respective agent SHALL return a descriptive parse error to the Orchestrator.
