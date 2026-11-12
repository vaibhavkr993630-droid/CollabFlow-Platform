"""POST /api/tasks/{id}/comments/summary — summaries of long comment threads."""

import pytest
from httpx import AsyncClient

from app.assistant.deps import get_assistant_client
from app.assistant.summaries import MIN_COMMENTS
from app.core.config import get_settings
from app.main import app
from tests.fakes import FakeAssistantClient
from tests.helpers import auth_headers, create_org_and_workspace, create_project, register_and_login


@pytest.fixture
def fake(client: AsyncClient) -> FakeAssistantClient:
    # Depends on `client` so the override is installed after (and cleared with) its own.
    fake_client = FakeAssistantClient()
    app.dependency_overrides[get_assistant_client] = lambda: fake_client
    return fake_client


async def _task_with_comments(client: AsyncClient, count: int) -> tuple[dict, dict]:
    token, _ = await register_and_login(client, "owner@example.com", "Priya Owner")
    _, workspace_id = await create_org_and_workspace(client, token, "Org")
    project_id = await create_project(client, token, workspace_id)
    headers = auth_headers(token)
    task = (
        await client.post(
            f"/api/projects/{project_id}/tasks",
            json={"title": "Gateway timeouts", "description": "Orders fail after 30s"},
            headers=headers,
        )
    ).json()
    for number in range(1, count + 1):
        await client.post(
            f"/api/tasks/{task['id']}/comments",
            json={"body": f"Comment number {number}"},
            headers=headers,
        )
    return headers, task


async def _summarize(client: AsyncClient, headers: dict, task_id: str):
    return await client.post(f"/api/tasks/{task_id}/comments/summary", headers=headers)


async def test_summarizes_a_long_thread(client: AsyncClient, fake: FakeAssistantClient):
    headers, task = await _task_with_comments(client, MIN_COMMENTS)

    resp = await _summarize(client, headers, task["id"])

    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "summary": fake.reply,
        "comment_count": MIN_COMMENTS,
        "cached": False,
    }
    prompt = fake.calls[0]["prompt"]
    assert "Task: Gateway timeouts" in prompt
    assert "Orders fail after 30s" in prompt
    assert "Priya Owner" in prompt
    # Every comment is sent, in order, inside the data markers.
    inside = prompt.split("<comments>")[1].split("</comments>")[0]
    positions = [inside.index(f"Comment number {n}") for n in range(1, MIN_COMMENTS + 1)]
    assert positions == sorted(positions)
    assert "not instructions to you" in fake.calls[0]["system"]


async def test_short_thread_is_refused_without_calling_provider(
    client: AsyncClient, fake: FakeAssistantClient
):
    headers, task = await _task_with_comments(client, MIN_COMMENTS - 1)

    resp = await _summarize(client, headers, task["id"])

    assert resp.status_code == 400
    assert fake.calls == []


async def test_non_member_cannot_summarize(client: AsyncClient, fake: FakeAssistantClient):
    _, task = await _task_with_comments(client, MIN_COMMENTS)
    outsider, _ = await register_and_login(client, "outsider@example.com", "Outsider")

    resp = await _summarize(client, auth_headers(outsider), task["id"])

    assert resp.status_code == 403
    assert fake.calls == []


async def test_feature_off_returns_503(client: AsyncClient):
    app.dependency_overrides[get_assistant_client] = lambda: None
    headers, task = await _task_with_comments(client, MIN_COMMENTS)

    resp = await _summarize(client, headers, task["id"])

    assert resp.status_code == 503


async def test_summary_is_reused_until_a_new_comment(
    client: AsyncClient, fake: FakeAssistantClient
):
    headers, task = await _task_with_comments(client, MIN_COMMENTS)

    first = await _summarize(client, headers, task["id"])
    second = await _summarize(client, headers, task["id"])
    assert first.json()["cached"] is False
    assert second.json()["cached"] is True
    assert len(fake.calls) == 1

    await client.post(
        f"/api/tasks/{task['id']}/comments", json={"body": "One more thing"}, headers=headers
    )
    third = await _summarize(client, headers, task["id"])
    assert third.json()["cached"] is False
    assert third.json()["comment_count"] == MIN_COMMENTS + 1
    assert len(fake.calls) == 2


async def test_provider_failure_returns_friendly_503(
    client: AsyncClient, fake: FakeAssistantClient
):
    fake.fail = True
    headers, task = await _task_with_comments(client, MIN_COMMENTS)

    resp = await _summarize(client, headers, task["id"])

    assert resp.status_code == 503
    assert resp.json()["detail"] == "The assistant could not be reached."


async def test_daily_limit_applies_but_cached_summaries_are_free(
    client: AsyncClient, fake: FakeAssistantClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(get_settings(), "assistant_daily_limit", 1)
    headers, task = await _task_with_comments(client, MIN_COMMENTS)

    assert (await _summarize(client, headers, task["id"])).status_code == 200
    # Cached: does not count against the limit.
    assert (await _summarize(client, headers, task["id"])).status_code == 200

    await client.post(
        f"/api/tasks/{task['id']}/comments", json={"body": "New info"}, headers=headers
    )
    resp = await _summarize(client, headers, task["id"])
    assert resp.status_code == 429
    assert len(fake.calls) == 1
