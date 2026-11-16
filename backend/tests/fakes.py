"""Test doubles. The real provider is never called from tests."""

import hashlib
from dataclasses import dataclass, field

from app.assistant.client import AssistantUnavailableError


@dataclass
class FakeAssistantClient:
    """Records every request and returns a fixed reply, or fails when told to."""

    reply: str = "Summary: the team agreed on a fix."
    fail: bool = False
    calls: list[dict] = field(default_factory=list)
    embed_calls: list[list[str]] = field(default_factory=list)

    async def complete(
        self, *, system: str, prompt: str, max_tokens: int = 1024, json_mode: bool = False
    ) -> str:
        self.calls.append(
            {"system": system, "prompt": prompt, "max_tokens": max_tokens, "json_mode": json_mode}
        )
        if self.fail:
            raise AssistantUnavailableError("The assistant could not be reached.")
        return self.reply

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Deterministic fake vectors: texts sharing words get similar vectors."""
        self.embed_calls.append(list(texts))
        if self.fail:
            raise AssistantUnavailableError("The assistant could not be reached.")
        return [fake_vector(text) for text in texts]


def fake_vector(text: str) -> list[float]:
    from app.models.search_document import EMBEDDING_DIMENSIONS

    vector = [0.0] * EMBEDDING_DIMENSIONS
    for word in text.lower().split():
        vector[int(hashlib.sha256(word.encode()).hexdigest(), 16) % EMBEDDING_DIMENSIONS] += 1.0
    vector[0] += 0.01  # never all zeros, which cosine distance cannot handle
    return vector
