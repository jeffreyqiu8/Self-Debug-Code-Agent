"""Code generation agent powered by an LLM."""

from __future__ import annotations

from agents.llm_client import LLMClient
from agents.response_parser import extract_code_block
from models import GenerationResult


class CodeGeneratorAgent:
    """Generates initial code solutions and unit tests via an LLM."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    def generate_code(self, task_description: str) -> GenerationResult:
        """Send *task_description* to the LLM and return a code solution.

        The LLM is instructed to reply with a single Python module wrapped in
        a markdown code fence.  The response is parsed to extract the code.

        Raises ``RuntimeError`` when the LLM call fails and ``ValueError``
        when the response cannot be parsed.
        """
        messages = [
            {
                "role": "system",
                "content": (
                    "You are an expert Python programmer. "
                    "Respond ONLY with a single Python code block "
                    "wrapped in markdown code fences (```python ... ```). "
                    "Do not include any explanation outside the code block."
                ),
            },
            {"role": "user", "content": task_description},
        ]

        raw_response = self._llm.chat(messages)
        code = extract_code_block(raw_response)
        return GenerationResult(code=code, raw_response=raw_response)

    def generate_tests(
        self, task_description: str, code: str
    ) -> GenerationResult:
        """Generate pytest-compatible unit tests for *code*.

        The prompt asks the LLM for a minimum of 3 test cases covering
        normal, edge, and error scenarios.
        """
        messages = [
            {
                "role": "system",
                "content": (
                    "You are an expert Python test engineer. "
                    "Given a task description and its implementation, "
                    "write pytest-compatible unit tests. "
                    "Include at least 3 test cases:\n"
                    "  1. A normal/happy-path case\n"
                    "  2. An edge-case\n"
                    "  3. An error/invalid-input case\n"
                    "Respond ONLY with a single Python code block "
                    "wrapped in markdown code fences (```python ... ```). "
                    "Do not include any explanation outside the code block."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Task description:\n{task_description}\n\n"
                    f"Implementation:\n```python\n{code}\n```"
                ),
            },
        ]

        raw_response = self._llm.chat(messages)
        test_code = extract_code_block(raw_response)
        return GenerationResult(code=test_code, raw_response=raw_response)
