"""
The one place the app talks to a text-generation provider.

Every assistant feature calls `AssistantClient.complete()`; nothing else in the app knows
which provider, model or key is in use. Swapping providers is a settings change, because
Google, Groq and Ollama all serve the same OpenAI-compatible /chat/completions API.
"""

import logging
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)


class AssistantUnavailableError(Exception):
    """The provider could not produce an answer. Routers turn this into a friendly 503."""


class AssistantClient(Protocol):
    async def complete(self, *, system: str, prompt: str, max_tokens: int = 1024) -> str: ...


class ChatCompletionsClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float,
        reasoning_effort: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_seconds
        self._reasoning_effort = reasoning_effort
        self._transport = transport  # tests pass httpx.MockTransport; None means real network

    async def complete(self, *, system: str, prompt: str, max_tokens: int = 1024) -> str:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens,
        }
        if self._reasoning_effort:
            payload["reasoning_effort"] = self._reasoning_effort
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as http:
                response = await http.post(
                    self._url,
                    json=payload,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
        except httpx.HTTPError as exc:
            logger.warning("Assistant provider unreachable: %s", type(exc).__name__)
            raise AssistantUnavailableError("The assistant could not be reached.") from exc

        if response.status_code == 429:
            raise AssistantUnavailableError(
                "The assistant's free quota is used up for now. Try again later."
            )
        if response.status_code >= 400:
            # Body excerpt only: never log the request, which may contain user content.
            logger.warning(
                "Assistant provider error %s: %s", response.status_code, response.text[:300]
            )
            raise AssistantUnavailableError("The assistant returned an error.")

        try:
            choice = response.json()["choices"][0]
            text = choice["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise AssistantUnavailableError("The assistant sent an unexpected reply.") from exc
        if choice.get("finish_reason") == "length":
            # Models that think before answering spend part of max_tokens on hidden reasoning.
            # A cut-off reply must never be shown or cached as if it were complete.
            raise AssistantUnavailableError("The assistant's reply was cut off. Try again.")
        if not text or not text.strip():
            raise AssistantUnavailableError("The assistant returned an empty reply.")
        return text.strip()
