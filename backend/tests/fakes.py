"""Test doubles. The real provider is never called from tests."""

from dataclasses import dataclass, field

from app.assistant.client import AssistantUnavailableError


@dataclass
class FakeAssistantClient:
    """Records every request and returns a fixed reply, or fails when told to."""

    reply: str = "Summary: the team agreed on a fix."
    fail: bool = False
    calls: list[dict] = field(default_factory=list)

    async def complete(self, *, system: str, prompt: str, max_tokens: int = 1024) -> str:
        self.calls.append({"system": system, "prompt": prompt, "max_tokens": max_tokens})
        if self.fail:
            raise AssistantUnavailableError("The assistant could not be reached.")
        return self.reply
