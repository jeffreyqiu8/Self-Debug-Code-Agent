"""LLM client wrapping the OpenAI Python SDK."""

from __future__ import annotations

import openai


class LLMClient:
    """Thin wrapper around the OpenAI chat completions API.

    Supports any OpenAI-compatible endpoint via *base_url*.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        model: str = "gpt-4",
    ) -> None:
        self.model = model
        kwargs: dict = {"api_key": api_key}
        if base_url is not None:
            kwargs["base_url"] = base_url
        self._client = openai.OpenAI(**kwargs)

    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.2,
    ) -> str:
        """Send a chat completion request and return the assistant message.

        Raises a descriptive ``RuntimeError`` when the API call fails.
        """
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
            )
            return response.choices[0].message.content or ""
        except openai.APIError as exc:
            raise RuntimeError(
                f"LLM API error ({type(exc).__name__}): {exc}"
            ) from exc
