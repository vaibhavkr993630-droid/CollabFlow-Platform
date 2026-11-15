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
    async def complete(
        self, *, system: str, prompt: str, max_tokens: int = 1024, json_mode: bool = False
    ) -> str: ...


class _RetryableError(AssistantUnavailableError):
    """Busy, rate-limited, timed out or unreachable: worth trying the backup model."""


class ChatCompletionsClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float,
        fallback_model: str | None = None,
        reasoning_effort: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._api_key = api_key
        self._models = [model] + ([fallback_model] if fallback_model else [])
        self._timeout = timeout_seconds
        self._reasoning_effort = reasoning_effort
        self._transport = transport  # tests pass httpx.MockTransport; None means real network

    async def complete(
        self, *, system: str, prompt: str, max_tokens: int = 1024, json_mode: bool = False
    ) -> str:
        """
        Returns the reply text. With json_mode, the provider is asked to reply with a JSON
        object only; callers still validate it, since the content is not guaranteed.

        Free tiers get overloaded (503 "high demand", 429, very slow replies). When the main
        model fails that way, the same request is tried once on the backup model. Errors that a
        retry cannot fix (bad request, cut-off or unreadable reply) fail straight away.
        """
        last_error: _RetryableError | None = None
        for model in self._models:
            try:
                return await self._complete_once(
                    model, system=system, prompt=prompt, max_tokens=max_tokens, json_mode=json_mode
                )
            except _RetryableError as exc:
                logger.warning("Assistant model %s unavailable: %s", model, exc)
                last_error = exc
        raise AssistantUnavailableError(str(last_error)) from last_error

    async def _complete_once(
        self, model: str, *, system: str, prompt: str, max_tokens: int, json_mode: bool
    ) -> str:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens,
        }
        if self._reasoning_effort:
            payload["reasoning_effort"] = self._reasoning_effort
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
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
            raise _RetryableError("The assistant could not be reached.") from exc

        if response.status_code == 429:
            raise _RetryableError("The assistant's free quota is used up for now. Try again later.")
        if response.status_code >= 500:
            raise _RetryableError("The assistant is busy right now. Try again in a minute.")
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
