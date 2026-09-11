import pytest
from httpx import AsyncClient

from tests.helpers import (
    auth_headers,
    create_org_and_workspace,
    create_project,
    register_and_login,
)

pytestmark = pytest.mark.asyncio


async def _setup_project(
    client: AsyncClient, owner_email: str = "owner@example.com"
) -> tuple[str, str]:
    """Registers an owner, creates an org/workspace/project, returns (owner_token, project_id)."""
    token, _ = await register_and_login(client, owner_email, "Owner")
    _, workspace_id = await create_org_and_workspace(client, token, "Acme")
    project_id = await create_project(client, token, workspace_id)
    return token, project_id


async def test_create_and_list_tasks(client: AsyncClient):
    token, project_id = await _setup_project(client)

    resp = await client.post(
        f"/api/projects/{project_id}/tasks",
        json={"title": "Set up CI", "priority": "high"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201
    task = resp.json()
    assert task["status"] == "todo"
    assert task["priority"] == "high"
    assert task["position"] == 1

    list_resp = await client.get(
        f"/api/projects/{project_id}/tasks", headers=auth_headers(token)
    )
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


async def test_assignee_must_be_project_member(client: AsyncClient):
    token, project_id = await _setup_project(client)
    _, outsider_id = await register_and_login(client, "outsider@example.com", "Outsider")

    resp = await client.post(
        f"/api/projects/{project_id}/tasks",
        json={"title": "Do the thing", "assignee_id": outsider_id},
        headers=auth_headers(token),
    )
    assert resp.status_code == 400


async def test_update_task_status(client: AsyncClient):
    token, project_id = await _setup_project(client)
    task = (
        await client.post(
            f"/api/projects/{project_id}/tasks",
            json={"title": "Ship feature"},
            headers=auth_headers(token),
        )
    ).json()

    resp = await client.patch(
        f"/api/tasks/{task['id']}",
        json={"status": "in_progress"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_progress"


async def test_non_member_cannot_view_task(client: AsyncClient):
    token, project_id = await _setup_project(client)
    outsider_token, _ = await register_and_login(client, "outsider@example.com", "Outsider")
    task = (
        await client.post(
            f"/api/projects/{project_id}/tasks",
            json={"title": "Ship feature"},
            headers=auth_headers(token),
        )
    ).json()

    resp = await client.get(f"/api/tasks/{task['id']}", headers=auth_headers(outsider_token))
    assert resp.status_code == 403


async def test_member_cannot_delete_but_admin_can(client: AsyncClient):
    owner_token, project_id = await _setup_project(client)
    member_token, _ = await register_and_login(client, "member@example.com", "Member")
    await client.post(
        f"/api/projects/{project_id}/members",
        json={"email": "member@example.com", "role": "member"},
        headers=auth_headers(owner_token),
    )
    task = (
        await client.post(
            f"/api/projects/{project_id}/tasks",
            json={"title": "Ship feature"},
            headers=auth_headers(owner_token),
        )
    ).json()

    forbidden = await client.delete(
        f"/api/tasks/{task['id']}", headers=auth_headers(member_token)
    )
    assert forbidden.status_code == 403

    allowed = await client.delete(
        f"/api/tasks/{task['id']}", headers=auth_headers(owner_token)
    )
    assert allowed.status_code == 204


async def test_subtask_must_belong_to_same_project(client: AsyncClient):
    token, project_id = await _setup_project(client)
    other_project_id = await create_project(
        client,
        token,
        (await create_org_and_workspace(client, token, "Other Org"))[1],
        name="Other Project",
    )

    other_task = (
        await client.post(
            f"/api/projects/{other_project_id}/tasks",
            json={"title": "Unrelated task"},
            headers=auth_headers(token),
        )
    ).json()

    resp = await client.post(
        f"/api/projects/{project_id}/tasks",
        json={"title": "Subtask", "parent_task_id": other_task["id"]},
        headers=auth_headers(token),
    )
    assert resp.status_code == 400


async def test_list_subtasks(client: AsyncClient):
    token, project_id = await _setup_project(client)
    parent = (
        await client.post(
            f"/api/projects/{project_id}/tasks",
            json={"title": "Parent task"},
            headers=auth_headers(token),
        )
    ).json()
    await client.post(
        f"/api/projects/{project_id}/tasks",
        json={"title": "Child task", "parent_task_id": parent["id"]},
        headers=auth_headers(token),
    )

    resp = await client.get(
        f"/api/tasks/{parent['id']}/subtasks", headers=auth_headers(token)
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["title"] == "Child task"


async def test_label_create_requires_admin(client: AsyncClient):
    owner_token, project_id = await _setup_project(client)
    member_token, _ = await register_and_login(client, "member@example.com", "Member")
    await client.post(
        f"/api/projects/{project_id}/members",
        json={"email": "member@example.com", "role": "member"},
        headers=auth_headers(owner_token),
    )

    forbidden = await client.post(
        f"/api/projects/{project_id}/labels",
        json={"name": "bug", "color": "#ff0000"},
        headers=auth_headers(member_token),
    )
    assert forbidden.status_code == 403

    allowed = await client.post(
        f"/api/projects/{project_id}/labels",
        json={"name": "bug", "color": "#ff0000"},
        headers=auth_headers(owner_token),
    )
    assert allowed.status_code == 201

    listed = await client.get(
        f"/api/projects/{project_id}/labels", headers=auth_headers(member_token)
    )
    assert listed.status_code == 200
    assert len(listed.json()) == 1


async def test_duplicate_label_name_rejected(client: AsyncClient):
    token, project_id = await _setup_project(client)
    await client.post(
        f"/api/projects/{project_id}/labels",
        json={"name": "bug", "color": "#ff0000"},
        headers=auth_headers(token),
    )
    resp = await client.post(
        f"/api/projects/{project_id}/labels",
        json={"name": "bug", "color": "#00ff00"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 409


async def test_comment_create_and_list(client: AsyncClient):
    token, project_id = await _setup_project(client)
    task = (
        await client.post(
            f"/api/projects/{project_id}/tasks",
            json={"title": "Ship feature"},
            headers=auth_headers(token),
        )
    ).json()

    resp = await client.post(
        f"/api/tasks/{task['id']}/comments",
        json={"body": "Looks good to me"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201

    listed = await client.get(
        f"/api/tasks/{task['id']}/comments", headers=auth_headers(token)
    )
    assert listed.status_code == 200
    assert listed.json()[0]["body"] == "Looks good to me"


async def test_non_member_cannot_comment(client: AsyncClient):
    token, project_id = await _setup_project(client)
    outsider_token, _ = await register_and_login(client, "outsider@example.com", "Outsider")
    task = (
        await client.post(
            f"/api/projects/{project_id}/tasks",
            json={"title": "Ship feature"},
            headers=auth_headers(token),
        )
    ).json()

    resp = await client.post(
        f"/api/tasks/{task['id']}/comments",
        json={"body": "sneaky comment"},
        headers=auth_headers(outsider_token),
    )
    assert resp.status_code == 403
