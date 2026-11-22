"""POST /api/projects/{id}/digest — a recap of recent changes, without deleted tasks."""

from datetime import date, timedelta

import pytest
from httpx import AsyncClient

from app.assistant import digest
from app.assistant.deps import get_assistant_client
from app.main import app
from app.services import comment_service, task_service
from tests.fakes import FakeAssistantClient
from tests.helpers import auth_headers, create_org_and_workspace, create_project, register_and_login


@pytest.fixture
def fake(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> FakeAssistantClient:
    fake_client = FakeAssistantClient(reply="Summary: a busy week.")
    app.dependency_overrides[get_assistant_client] = lambda: fake_client
    monkeypatch.setattr(task_service, "queue_task_indexing", lambda _id: None)
    monkeypatch.setattr(comment_service, "queue_comment_indexing", lambda _id: None)
    return fake_client


async def _setup(client: AsyncClient) -> tuple[dict, str, str, dict]:
    token, priya_id = await register_and_login(client, "priya@example.com", "Priya Sharma")
    _, arjun_id = await register_and_login(client, "arjun@example.com", "Arjun Mehta")
    _, workspace_id = await create_org_and_workspace(client, token, "Org")
    project_id = await create_project(client, token, workspace_id)
    headers = auth_headers(token)
    await client.post(
        f"/api/projects/{project_id}/members", json={"email": "arjun@example.com"}, headers=headers
    )
    return headers, project_id, workspace_id, {"priya": priya_id, "arjun": arjun_id}


async def _task(client, headers, project_id, title, **fields) -> dict:
    resp = await client.post(
        f"/api/projects/{project_id}/tasks", json={"title": title, **fields}, headers=headers
    )
    return resp.json()


async def _digest(client, headers, project_id, days=7):
    return await client.post(
        f"/api/projects/{project_id}/digest", json={"days": days}, headers=headers
    )


async def test_recap_input_is_readable_and_complete(client: AsyncClient, fake: FakeAssistantClient):
    headers, project_id, _, ids = await _setup(client)
    task = await _task(client, headers, project_id, "Gateway timeouts")
    await client.patch(
        f"/api/tasks/{task['id']}",
        json={"status": "in_progress", "assignee_id": ids["arjun"]},
        headers=headers,
    )
    await client.post(
        f"/api/tasks/{task['id']}/comments",
        json={"body": "Decided: raise the timeout to 60s"},
        headers=headers,
    )

    resp = await _digest(client, headers, project_id)

    assert resp.status_code == 200, resp.text
    assert resp.json()["digest"] == fake.reply
    assert resp.json()["cached"] is False
    prompt = fake.calls[0]["prompt"]
    assert "Priya Sharma created task 'Gateway timeouts'" in prompt
    assert "status: todo -> in_progress" in prompt
    assert "assignee: nobody -> Arjun Mehta" in prompt  # a name, never a raw id
    assert "Priya Sharma on 'Gateway timeouts': Decided: raise the timeout to 60s" in prompt
    assert "commented on" not in prompt  # comments appear once, with their text
    assert "arjun@example.com" not in prompt  # member invites are described without emails
    assert "not instructions to you" in fake.calls[0]["system"]


async def test_deleted_tasks_never_reach_the_recap(client: AsyncClient, fake: FakeAssistantClient):
    headers, project_id, _, _ = await _setup(client)
    await _task(client, headers, project_id, "Visible work")
    secret = await _task(client, headers, project_id, "Secret plan X", description="hush")
    await client.patch(
        f"/api/tasks/{secret['id']}", json={"description": "even more secret"}, headers=headers
    )
    await client.delete(f"/api/tasks/{secret['id']}", headers=headers)

    await _digest(client, headers, project_id)

    prompt = fake.calls[0]["prompt"]
    assert "Visible work" in prompt
    for leaked in ("Secret plan X", "hush", "even more secret"):
        assert leaked not in prompt
    assert "Tasks deleted in the period: 1" in prompt


async def test_facts_are_counted_by_the_database(client: AsyncClient, fake: FakeAssistantClient):
    headers, project_id, _, _ = await _setup(client)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    await _task(client, headers, project_id, "Late one", due_date=yesterday)
    await _task(client, headers, project_id, "Late but done", due_date=yesterday, status="done")
    await _task(client, headers, project_id, "Nobody owns this", priority="urgent")

    await _digest(client, headers, project_id)

    prompt = fake.calls[0]["prompt"]
    assert f"Overdue open tasks (1): 'Late one' (due {yesterday})" in prompt
    assert "Urgent or high-priority open tasks with no assignee (1): 'Nobody owns this'" in prompt


@pytest.mark.parametrize(
    ("deleted", "expected"),
    [
        (0, "Nothing changed in this project in the last 7 days."),
        (1, "The only change in the last 7 days: 1 task was deleted."),
        (2, "The only change in the last 7 days: 2 tasks were deleted."),
    ],
)
async def test_quiet_periods_are_answered_without_the_model(
    monkeypatch: pytest.MonkeyPatch, deleted: int, expected: str
):
    async def quiet(_db, _project_id, _days):
        return {"activity": [], "comments": [], "deleted": deleted}

    monkeypatch.setattr(digest, "_gather", quiet)
    fake = FakeAssistantClient()

    text, count, cached = await digest.project_digest(
        None, None, fake, project_id=None, days=7, user=None
    )

    assert (text, count, cached) == (expected, 0, False)
    assert fake.calls == []


async def test_recap_is_reused_until_something_new_happens(
    client: AsyncClient, fake: FakeAssistantClient
):
    headers, project_id, _, _ = await _setup(client)
    task = await _task(client, headers, project_id, "Gateway timeouts")

    assert (await _digest(client, headers, project_id)).json()["cached"] is False
    assert (await _digest(client, headers, project_id)).json()["cached"] is True
    assert len(fake.calls) == 1

    await client.patch(f"/api/tasks/{task['id']}", json={"status": "done"}, headers=headers)
    assert (await _digest(client, headers, project_id)).json()["cached"] is False
    assert len(fake.calls) == 2


async def test_another_projects_activity_is_never_included(
    client: AsyncClient, fake: FakeAssistantClient
):
    headers, project_id, workspace_id, _ = await _setup(client)
    other = await create_project(client, headers["Authorization"].split()[1], workspace_id, "B")
    await _task(client, headers, other, "Other team's secret task")
    await _task(client, headers, project_id, "Our task")

    await _digest(client, headers, project_id)

    prompt = fake.calls[0]["prompt"]
    assert "Our task" in prompt
    assert "Other team's secret task" not in prompt


async def test_access_input_and_failures(client: AsyncClient, fake: FakeAssistantClient):
    headers, project_id, _, _ = await _setup(client)
    outsider, _ = await register_and_login(client, "outsider@example.com", "Outsider")

    assert (await _digest(client, auth_headers(outsider), project_id)).status_code == 403
    assert (await _digest(client, headers, project_id, days=0)).status_code == 422
    assert (await _digest(client, headers, project_id, days=31)).status_code == 422
    assert fake.calls == []

    fake.fail = True
    resp = await _digest(client, headers, project_id)
    assert resp.status_code == 503
    assert resp.json()["detail"] == "The assistant could not be reached."

    app.dependency_overrides[get_assistant_client] = lambda: None
    assert (await _digest(client, headers, project_id)).status_code == 503
