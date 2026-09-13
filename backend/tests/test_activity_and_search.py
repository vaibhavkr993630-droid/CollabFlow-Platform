import pytest
from httpx import AsyncClient

from tests.helpers import auth_headers, create_org_and_workspace, create_project, register_and_login

pytestmark = pytest.mark.asyncio


async def _setup_project(client: AsyncClient) -> tuple[str, str]:
    token, _ = await register_and_login(client, "owner@example.com", "Owner")
    _, workspace_id = await create_org_and_workspace(client, token, "Acme")
    project_id = await create_project(client, token, workspace_id)
    return token, project_id


async def test_filter_tasks_by_status_and_priority(client: AsyncClient):
    token, project_id = await _setup_project(client)
    headers = auth_headers(token)
    await client.post(
        f"/api/projects/{project_id}/tasks",
        json={"title": "Task A", "status": "todo", "priority": "low"},
        headers=headers,
    )
    await client.post(
        f"/api/projects/{project_id}/tasks",
        json={"title": "Task B", "status": "in_progress", "priority": "urgent"},
        headers=headers,
    )

    resp = await client.get(
        f"/api/projects/{project_id}/tasks",
        params={"status": "in_progress"},
        headers=headers,
    )
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Task B"

    resp = await client.get(
        f"/api/projects/{project_id}/tasks", params={"priority": "urgent"}, headers=headers
    )
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Task B"


async def test_search_tasks_by_title(client: AsyncClient):
    token, project_id = await _setup_project(client)
    headers = auth_headers(token)
    await client.post(
        f"/api/projects/{project_id}/tasks", json={"title": "Fix login bug"}, headers=headers
    )
    await client.post(
        f"/api/projects/{project_id}/tasks", json={"title": "Write docs"}, headers=headers
    )

    resp = await client.get(
        f"/api/projects/{project_id}/tasks", params={"search": "login"}, headers=headers
    )
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Fix login bug"


async def test_filter_tasks_by_label(client: AsyncClient):
    token, project_id = await _setup_project(client)
    headers = auth_headers(token)
    label = (
        await client.post(
            f"/api/projects/{project_id}/labels",
            json={"name": "bug", "color": "#ff0000"},
            headers=headers,
        )
    ).json()
    task = (
        await client.post(
            f"/api/projects/{project_id}/tasks", json={"title": "Buggy task"}, headers=headers
        )
    ).json()
    await client.post(
        f"/api/projects/{project_id}/tasks", json={"title": "Clean task"}, headers=headers
    )

    attach_resp = await client.patch(
        f"/api/tasks/{task['id']}", json={"label_ids": [label["id"]]}, headers=headers
    )
    assert attach_resp.json()["labels"][0]["name"] == "bug"

    resp = await client.get(
        f"/api/projects/{project_id}/tasks", params={"label_id": label["id"]}, headers=headers
    )
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Buggy task"


async def test_sort_tasks_by_due_date(client: AsyncClient):
    token, project_id = await _setup_project(client)
    headers = auth_headers(token)
    await client.post(
        f"/api/projects/{project_id}/tasks",
        json={"title": "Later", "due_date": "2026-12-31"},
        headers=headers,
    )
    await client.post(
        f"/api/projects/{project_id}/tasks",
        json={"title": "Sooner", "due_date": "2026-09-01"},
        headers=headers,
    )

    resp = await client.get(
        f"/api/projects/{project_id}/tasks",
        params={"sort_by": "due_date", "sort_order": "asc"},
        headers=headers,
    )
    titles = [t["title"] for t in resp.json()["items"]]
    assert titles == ["Sooner", "Later"]


async def test_pagination(client: AsyncClient):
    token, project_id = await _setup_project(client)
    headers = auth_headers(token)
    for i in range(5):
        await client.post(
            f"/api/projects/{project_id}/tasks", json={"title": f"Task {i}"}, headers=headers
        )

    resp = await client.get(
        f"/api/projects/{project_id}/tasks",
        params={"page": 1, "page_size": 2},
        headers=headers,
    )
    body = resp.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2
    assert body["page"] == 1


async def test_project_activity_log_records_actions(client: AsyncClient):
    token, project_id = await _setup_project(client)
    headers = auth_headers(token)

    task = (
        await client.post(
            f"/api/projects/{project_id}/tasks", json={"title": "Ship feature"}, headers=headers
        )
    ).json()
    await client.patch(
        f"/api/tasks/{task['id']}", json={"status": "in_progress"}, headers=headers
    )
    await client.post(
        f"/api/tasks/{task['id']}/comments", json={"body": "Nice"}, headers=headers
    )

    resp = await client.get(f"/api/projects/{project_id}/activity", headers=headers)
    body = resp.json()
    actions = [entry["action"] for entry in body["items"]]
    assert "project_created" in actions
    assert "task_created" in actions
    assert "task_updated" in actions
    assert "comment_added" in actions
    # newest first
    assert body["items"][0]["action"] == "comment_added"


async def test_task_activity_log_scoped_to_one_task(client: AsyncClient):
    token, project_id = await _setup_project(client)
    headers = auth_headers(token)

    task_a = (
        await client.post(
            f"/api/projects/{project_id}/tasks", json={"title": "Task A"}, headers=headers
        )
    ).json()
    task_b = (
        await client.post(
            f"/api/projects/{project_id}/tasks", json={"title": "Task B"}, headers=headers
        )
    ).json()
    await client.patch(f"/api/tasks/{task_a['id']}", json={"status": "done"}, headers=headers)

    resp = await client.get(f"/api/tasks/{task_a['id']}/activity", headers=headers)
    body = resp.json()
    assert all(entry["task_id"] == task_a["id"] for entry in body["items"])
    assert task_b["title"] == "Task B"  # sanity: task_b exists but shouldn't appear above


async def test_activity_log_survives_task_deletion(client: AsyncClient):
    token, project_id = await _setup_project(client)
    headers = auth_headers(token)

    task = (
        await client.post(
            f"/api/projects/{project_id}/tasks", json={"title": "Temp task"}, headers=headers
        )
    ).json()
    delete_resp = await client.delete(f"/api/tasks/{task['id']}", headers=headers)
    assert delete_resp.status_code == 204

    resp = await client.get(f"/api/projects/{project_id}/activity", headers=headers)
    actions = [entry["action"] for entry in resp.json()["items"]]
    assert "task_deleted" in actions


async def test_non_member_cannot_view_activity(client: AsyncClient):
    _, project_id = await _setup_project(client)
    outsider_token, _ = await register_and_login(client, "outsider@example.com", "Outsider")

    resp = await client.get(
        f"/api/projects/{project_id}/activity", headers=auth_headers(outsider_token)
    )
    assert resp.status_code == 403
