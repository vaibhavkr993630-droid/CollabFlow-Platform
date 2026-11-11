"""The shared assistant layer: on/off switch, provider client, and per-user daily limit."""

import json
import uuid
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from httpx import AsyncClient

from app.assistant.client import AssistantUnavailableError, ChatCompletionsClient
from app.assistant.deps import enforce_daily_limit, get_assistant_client, require_assistant
from app.core.config import get_settings
from app.core.redis import get_redis_client

settings = get_settings()


# --- on/off switch ---------------------------------------------------------------


async def test_features_report_assistant_off_without_key(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "assistant_api_key", None)
    resp = await client.get("/api/features")
    assert resp.status_code == 200
    assert resp.json() == {"assistant": False}


async def test_features_report_assistant_on_with_key(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "assistant_api_key", "test-key")
    resp = await client.get("/api/features")
    assert resp.json() == {"assistant": True}


def test_require_assistant_refuses_when_off(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "assistant_api_key", None)
    with pytest.raises(HTTPException) as exc_info:
        require_assistant(get_assistant_client())
    assert exc_info.value.status_code == 503


# --- provider client, against a simulated provider ------------------------------------


def _client(handler) -> ChatCompletionsClient:
    return ChatCompletionsClient(
        base_url="https://provider.test/v1/",
        api_key="secret-key",
        model="test-model",
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    )


def _reply(content) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


async def test_client_sends_openai_style_request_and_returns_text():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["Authorization"]
        seen["body"] = json.loads(request.content)
        return _reply("  A short answer.  ")

    text = await _client(handler).complete(system="Be brief.", prompt="Hi", max_tokens=50)

    assert text == "A short answer."
    assert seen["url"] == "https://provider.test/v1/chat/completions"
    assert seen["auth"] == "Bearer secret-key"
    assert seen["body"]["model"] == "test-model"
    assert seen["body"]["max_tokens"] == 50
    assert seen["body"]["messages"] == [
        {"role": "system", "content": "Be brief."},
        {"role": "user", "content": "Hi"},
    ]


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(429, json={"error": "quota"}),
        httpx.Response(500, text="boom"),
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"choices": []}),
        _reply(""),
        _reply(None),
    ],
    ids=["quota", "server-error", "not-json", "no-choices", "empty", "null"],
)
async def test_client_turns_bad_replies_into_unavailable(response: httpx.Response):
    with pytest.raises(AssistantUnavailableError):
        await _client(lambda _request: response).complete(system="s", prompt="p")


async def test_client_turns_network_failure_into_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    with pytest.raises(AssistantUnavailableError):
        await _client(handler).complete(system="s", prompt="p")


# --- per-user daily limit, against real Redis ------------------------------------------


async def test_daily_limit_blocks_after_limit_per_user(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "assistant_daily_limit", 2)
    redis = get_redis_client()
    alice = SimpleNamespace(id=uuid.uuid4())
    bob = SimpleNamespace(id=uuid.uuid4())

    try:
        await enforce_daily_limit(current_user=alice, redis=redis)
        await enforce_daily_limit(current_user=alice, redis=redis)
        with pytest.raises(HTTPException) as exc_info:
            await enforce_daily_limit(current_user=alice, redis=redis)
        assert exc_info.value.status_code == 429

        # Another user's quota is separate.
        assert await enforce_daily_limit(current_user=bob, redis=redis) is bob

        # The counter cleans itself up instead of living forever.
        keys = await redis.keys(f"assistant:usage:{alice.id}:*")
        assert len(keys) == 1
        assert 0 < await redis.ttl(keys[0]) <= 2 * 24 * 60 * 60
    finally:
        for user in (alice, bob):
            for key in await redis.keys(f"assistant:usage:{user.id}:*"):
                await redis.delete(key)
