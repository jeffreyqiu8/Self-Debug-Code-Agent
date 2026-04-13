"""CLI entry point for the Autonomous Self-Debugging AI Code Agent."""

from __future__ import annotations

import argparse
import json
import os
import sys

from models import OrchestratorConfig, TaskInput, serialize
from orchestrator import Orchestrator


DEMO_TASKS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo_tasks")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Autonomous Self-Debugging AI Code Agent",
    )
    parser.add_argument(
        "--task",
        type=str,
        default=None,
        help="Programming task description. If omitted, demo tasks are run.",
    )
    parser.add_argument(
        "--tests",
        type=str,
        default=None,
        help="Path to a file containing unit test code for the task.",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help="Maximum number of debug-patch iterations (default: 5).",
    )
    return parser.parse_args(argv)


def _load_demo_tasks() -> list[TaskInput]:
    """Load demo task JSON files from the demo_tasks/ directory."""
    tasks: list[TaskInput] = []
    if not os.path.isdir(DEMO_TASKS_DIR):
        print(f"[main] Demo tasks directory not found: {DEMO_TASKS_DIR}", file=sys.stderr)
        return tasks

    for filename in sorted(os.listdir(DEMO_TASKS_DIR)):
        if not filename.endswith(".json"):
            continue
        filepath = os.path.join(DEMO_TASKS_DIR, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "task" not in data:
                print(f"[main] Skipping {filename}: missing 'task' field.", file=sys.stderr)
                continue
            tasks.append(TaskInput(task=data["task"], tests=data.get("tests")))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[main] Skipping {filename}: {exc}", file=sys.stderr)
    return tasks


def _build_config(args: argparse.Namespace) -> OrchestratorConfig:
    """Build an OrchestratorConfig from CLI args and environment variables."""
    config = OrchestratorConfig(
        llm_api_key=os.environ.get("OPENAI_API_KEY", ""),
        llm_base_url=os.environ.get("OPENAI_BASE_URL"),
        llm_model=os.environ.get("LLM_MODEL", "gpt-4"),
    )
    if args.max_iterations is not None:
        config.max_iterations = args.max_iterations
    return config


def _run_task(orchestrator: Orchestrator, task_input: TaskInput) -> dict:
    """Run a single task through the orchestrator and return the JSON-serialisable result."""
    result = orchestrator.run(task_input)
    return json.loads(serialize(result))


def main(argv: list[str] | None = None) -> None:
    """Entry point: parse args, run tasks, print JSON results to stdout."""
    args = parse_args(argv)
    config = _build_config(args)
    orchestrator = Orchestrator(config)

    if args.task is not None:
        # --- Single task from CLI ---
        tests: str | None = None
        if args.tests is not None:
            try:
                with open(args.tests, "r", encoding="utf-8") as f:
                    tests = f.read()
            except OSError as exc:
                print(f"[main] Error reading tests file: {exc}", file=sys.stderr)
                sys.exit(1)

        task_input = TaskInput(task=args.task, tests=tests)
        result = _run_task(orchestrator, task_input)
        print(json.dumps(result, indent=2))
    else:
        # --- Demo tasks ---
        demo_tasks = _load_demo_tasks()
        if not demo_tasks:
            print("[main] No demo tasks found. Provide a --task argument or add JSON files to demo_tasks/.")
            sys.exit(0)

        results: list[dict] = []
        for i, task_input in enumerate(demo_tasks, 1):
            print(f"\n{'#'*60}")
            print(f"# Demo Task {i}: {task_input.task[:80]}…")
            print(f"{'#'*60}\n")
            result = _run_task(orchestrator, task_input)
            results.append(result)

        print("\n" + json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
