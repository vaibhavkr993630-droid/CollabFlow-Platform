"""GET /api/projects/{id}/tasks/similar — finding tasks by meaning, inside one project only."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant import indexing
from app.assistant.deps import get_assistant_client
from app.core.config import get_settings
from app.core.redis import get_redis_client
from app.main import app
from app.services import comment_service, task_service
from tests.fakes import FakeAssistantClient
from tests.helpers import auth_headers, create_org_and_workspace, create_project, register_and_login


@pytest.fixture
def fake(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> FakeAssistantClient:
    fake_client = FakeAssistantClient()
    app.dependency_overrides[get_assistant_client] = lambda: fake_client
    # Tests index explicitly instead of through Celery.
    monkeypatch.setattr(task_service, "queue_task_indexing", lambda _id: None)
    monkeypatch.setattr(comment_service, "queue_comment_indexing", lambda _id: None)
    return fake_client


async def _setup(client: AsyncClient) -> tuple[dict, str, str]:
    token, _ = await register_and_login(client, "owner@example.com", "Priya Sharma")
    _, workspace_id = await create_org_and_workspace(client, token, "Org")
    project_id = await create_project(client, token, workspace_id)
    return auth_headers(token), project_id, workspace_id


async def _task(client, headers, project_id, title, **fields) -> dict:
    resp = await client.post(
        f"/api/projects/{project_id}/tasks", json={"title": title, **fields}, headers=headers
    )
    return resp.json()


async def _search(client, headers, project_id, q, purpose="search"):
    return await client.get(
        f"/api/projects/{project_id}/tasks/similar",
        params={"q": q, "purpose": purpose},
        headers=headers,
    )


async def test_finds_tasks_and_surfaces_parents_of_subtasks_and_comments(
    client: AsyncClient, db_session: AsyncSession, fake: FakeAssistantClient
):
    headers, project_id, _ = await _setup(client)
    gateway = await _task(client, headers, project_id, "Payment gateway timeouts")
    mobile = await _task(client, headers, project_id, "Mobile app")
    child = await _task(
        client, headers, project_id, "Push notifications", parent_task_id=mobile["id"]
    )
    comment = (
        await client.post(
            f"/api/tasks/{gateway['id']}/comments",
            json={"body": "customers charged twice"},
            headers=headers,
        )
    ).json()
    for task_id in (gateway["id"], mobile["id"], child["id"]):
        await indexing.index_task(db_session, fake, uuid.UUID(task_id))
    await indexing.index_comment(db_session, fake, uuid.UUID(comment["id"]))

    # The fake gives identical vectors to identical text, so these are exact matches.
    resp = await _search(client, headers, project_id, "Push notifications")
    assert resp.status_code == 200, resp.text
    [hit] = resp.json()["results"]
    assert hit["id"] == mobile["id"]  # the subtask's parent, as on the board
    assert hit["matched_in"] == "task"

    comment_text = "Comment by Priya Sharma on 'Payment gateway timeouts': customers charged twice"
    [hit] = (await _search(client, headers, project_id, comment_text)).json()["results"]
    assert hit["id"] == gateway["id"]
    assert hit["matched_in"] == "comment"
    assert hit["matched_text"] == "Priya Sharma: customers charged twice"
    assert hit["similarity"] == pytest.approx(1.0)


async def test_never_returns_another_projects_tasks(
    client: AsyncClient, db_session: AsyncSession, fake: FakeAssistantClient
):
    headers, project_id, workspace_id = await _setup(client)
    other_project = await create_project(
        client, headers["Authorization"].split()[1], workspace_id, "Other"
    )
    secret = await _task(client, headers, other_project, "Quarterly budget numbers")
    await indexing.index_task(db_session, fake, uuid.UUID(secret["id"]))

    resp = await _search(client, headers, project_id, "Quarterly budget numbers")

    assert resp.json() == {"results": []}
    hits = (await _search(client, headers, other_project, "Quarterly budget numbers")).json()
    assert [h["id"] for h in hits["results"]] == [secret["id"]]


async def test_unrelated_queries_return_nothing(
    client: AsyncClient, db_session: AsyncSession, fake: FakeAssistantClient
):
    headers, project_id, _ = await _setup(client)
    task = await _task(client, headers, project_id, "Payment gateway timeouts")
    await indexing.index_task(db_session, fake, uuid.UUID(task["id"]))

    for purpose in ("search", "duplicate"):
        resp = await _search(client, headers, project_id, "office party planning", purpose)
        assert resp.json() == {"results": []}


async def test_non_member_is_refused_before_any_lookup(
    client: AsyncClient, fake: FakeAssistantClient
):
    _, project_id, _ = await _setup(client)
    outsider, _ = await register_and_login(client, "outsider@example.com", "Outsider")

    resp = await _search(client, auth_headers(outsider), project_id, "anything at all")

    assert resp.status_code == 403
    assert fake.embed_calls == []


async def test_feature_off_and_bad_input(client: AsyncClient, fake: FakeAssistantClient):
    headers, project_id, _ = await _setup(client)

    assert (await _search(client, headers, project_id, "ab")).status_code == 422
    assert (await _search(client, headers, project_id, "abc", "other")).status_code == 422

    app.dependency_overrides[get_assistant_client] = lambda: None
    assert (await _search(client, headers, project_id, "anything")).status_code == 503


async def test_search_has_its_own_daily_limit(
    client: AsyncClient, fake: FakeAssistantClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(get_settings(), "assistant_search_daily_limit", 2)
    headers, project_id, _ = await _setup(client)
    me = (await client.get("/api/auth/me", headers=headers)).json()

    assert (await _search(client, headers, project_id, "first")).status_code == 200
    assert (await _search(client, headers, project_id, "second")).status_code == 200
    resp = await _search(client, headers, project_id, "third")
    assert resp.status_code == 429
    assert "smart searches" in resp.json()["detail"]

    # Searching did not use up the separate text-generation budget.
    redis = get_redis_client()
    assert await redis.keys(f"assistant:usage:{me['id']}:*") == []
