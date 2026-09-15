import pytest
from httpx import AsyncClient

from tests.helpers import auth_headers, create_org_and_workspace, create_project, register_and_login

pytestmark = pytest.mark.asyncio


async def _setup_project(client: AsyncClient) -> tuple[str, str, str]:
    """Registers an owner, creates org/workspace/project, returns
    (owner_token, owner_id, project_id)."""
    token, user_id = await register_and_login(client, "notifyowner@example.com", "Owner")
    _, workspace_id = await create_org_and_workspace(client, token, "Acme")
    project_id = await create_project(client, token, workspace_id)
    return token, user_id, project_id


async def test_task_assignment_creates_notification(client: AsyncClient):
    owner_token, _, project_id = await _setup_project(client)
    member_token, member_id = await register_and_login(client, "assignee@example.com", "Assignee")
    await client.post(
        f"/api/projects/{project_id}/members",
        json={"email": "assignee@example.com", "role": "member"},
        headers=auth_headers(owner_token),
    )

    await client.post(
        f"/api/projects/{project_id}/tasks",
        json={"title": "Ship feature", "assignee_id": member_id},
        headers=auth_headers(owner_token),
    )

    resp = await client.get("/api/notifications", headers=auth_headers(member_token))
    body = resp.json()
    # 2, not 1: the project invite above also creates a notification for this same
    # user, in addition to the assignment.
    assert body["total"] == 2
    types = {item["type"] for item in body["items"]}
    assert types == {"project_invite", "task_assigned"}


async def test_self_assignment_does_not_notify(client: AsyncClient):
    owner_token, _, project_id = await _setup_project(client)

    await client.post(
        f"/api/projects/{project_id}/tasks",
        json={"title": "Do it myself"},
        headers=auth_headers(owner_token),
    )

    resp = await client.get("/api/notifications", headers=auth_headers(owner_token))
    assert resp.json()["total"] == 0


async def test_reassignment_notifies_new_assignee(client: AsyncClient):
    owner_token, owner_id, project_id = await _setup_project(client)
    member_token, member_id = await register_and_login(client, "assignee2@example.com", "Assignee2")
    await client.post(
        f"/api/projects/{project_id}/members",
        json={"email": "assignee2@example.com", "role": "member"},
        headers=auth_headers(owner_token),
    )

    task = (
        await client.post(
            f"/api/projects/{project_id}/tasks",
            json={"title": "Task", "assignee_id": owner_id},
            headers=auth_headers(owner_token),
        )
    ).json()
    await client.patch(
        f"/api/tasks/{task['id']}",
        json={"assignee_id": member_id},
        headers=auth_headers(owner_token),
    )

    resp = await client.get("/api/notifications", headers=auth_headers(member_token))
    body = resp.json()
    # 2, not 1: same reasoning as test_task_assignment_creates_notification above
    # — the project invite creates its own notification alongside the assignment.
    assert body["total"] == 2
    types = {item["type"] for item in body["items"]}
    assert types == {"project_invite", "task_assigned"}


async def test_workspace_invite_creates_notification(client: AsyncClient):
    owner_token, _ = await register_and_login(client, "wsinviteowner@example.com", "Owner")
    invitee_token, _ = await register_and_login(client, "wsinvitee@example.com", "Invitee")
    org_resp = await client.post(
        "/api/organizations", json={"name": "Acme"}, headers=auth_headers(owner_token)
    )
    org = org_resp.json()
    workspace = (
        await client.post(
            f"/api/organizations/{org['id']}/workspaces",
            json={"name": "Eng"},
            headers=auth_headers(owner_token),
        )
    ).json()

    await client.post(
        f"/api/workspaces/{workspace['id']}/members",
        json={"email": "wsinvitee@example.com", "role": "member"},
        headers=auth_headers(owner_token),
    )

    resp = await client.get("/api/notifications", headers=auth_headers(invitee_token))
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["type"] == "workspace_invite"


async def test_project_invite_creates_notification(client: AsyncClient):
    owner_token, _, project_id = await _setup_project(client)
    invitee_token, _ = await register_and_login(client, "projinvitee@example.com", "Invitee")

    await client.post(
        f"/api/projects/{project_id}/members",
        json={"email": "projinvitee@example.com", "role": "member"},
        headers=auth_headers(owner_token),
    )

    resp = await client.get("/api/notifications", headers=auth_headers(invitee_token))
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["type"] == "project_invite"


async def test_mention_in_comment_notifies_project_member(client: AsyncClient):
    owner_token, _, project_id = await _setup_project(client)
    member_token, _ = await register_and_login(client, "mentioned@example.com", "Mentioned")
    await client.post(
        f"/api/projects/{project_id}/members",
        json={"email": "mentioned@example.com", "role": "member"},
        headers=auth_headers(owner_token),
    )
    task = (
        await client.post(
            f"/api/projects/{project_id}/tasks",
            json={"title": "Task"},
            headers=auth_headers(owner_token),
        )
    ).json()

    await client.post(
        f"/api/tasks/{task['id']}/comments",
        json={"body": "hey @mentioned@example.com can you take a look?"},
        headers=auth_headers(owner_token),
    )

    resp = await client.get("/api/notifications", headers=auth_headers(member_token))
    body = resp.json()
    # 2, not 1: same reasoning as the assignment tests above — project invite +
    # the mention notification.
    assert body["total"] == 2
    types = {item["type"] for item in body["items"]}
    assert types == {"project_invite", "mention"}


async def test_mention_of_non_member_does_not_notify(client: AsyncClient):
    owner_token, _, project_id = await _setup_project(client)
    outsider_token, _ = await register_and_login(client, "outsider@example.com", "Outsider")
    task = (
        await client.post(
            f"/api/projects/{project_id}/tasks",
            json={"title": "Task"},
            headers=auth_headers(owner_token),
        )
    ).json()

    await client.post(
        f"/api/tasks/{task['id']}/comments",
        json={"body": "hey @outsider@example.com"},
        headers=auth_headers(owner_token),
    )

    resp = await client.get("/api/notifications", headers=auth_headers(outsider_token))
    assert resp.json()["total"] == 0


async def test_self_mention_does_not_notify(client: AsyncClient):
    owner_token, _, project_id = await _setup_project(client)
    task = (
        await client.post(
            f"/api/projects/{project_id}/tasks",
            json={"title": "Task"},
            headers=auth_headers(owner_token),
        )
    ).json()

    await client.post(
        f"/api/tasks/{task['id']}/comments",
        json={"body": "note to self @notifyowner@example.com"},
        headers=auth_headers(owner_token),
    )

    resp = await client.get("/api/notifications", headers=auth_headers(owner_token))
    assert resp.json()["total"] == 0


async def test_unread_count_and_mark_read(client: AsyncClient):
    owner_token, _, project_id = await _setup_project(client)
    member_token, member_id = await register_and_login(client, "reader@example.com", "Reader")
    await client.post(
        f"/api/projects/{project_id}/members",
        json={"email": "reader@example.com", "role": "member"},
        headers=auth_headers(owner_token),
    )
    await client.post(
        f"/api/projects/{project_id}/tasks",
        json={"title": "T1", "assignee_id": member_id},
        headers=auth_headers(owner_token),
    )
    await client.post(
        f"/api/projects/{project_id}/tasks",
        json={"title": "T2", "assignee_id": member_id},
        headers=auth_headers(owner_token),
    )

    # 3, not 2: project_invite (from adding the member above) + 2x task_assigned.
    unread = await client.get("/api/notifications/unread-count", headers=auth_headers(member_token))
    assert unread.json()["unread_count"] == 3

    notifications = (
        await client.get("/api/notifications", headers=auth_headers(member_token))
    ).json()["items"]
    first_id = notifications[0]["id"]

    read_resp = await client.post(
        f"/api/notifications/{first_id}/read", headers=auth_headers(member_token)
    )
    assert read_resp.status_code == 200
    assert read_resp.json()["read_at"] is not None

    unread = await client.get("/api/notifications/unread-count", headers=auth_headers(member_token))
    assert unread.json()["unread_count"] == 2


async def test_mark_all_read(client: AsyncClient):
    owner_token, _, project_id = await _setup_project(client)
    member_token, member_id = await register_and_login(client, "markall@example.com", "MarkAll")
    await client.post(
        f"/api/projects/{project_id}/members",
        json={"email": "markall@example.com", "role": "member"},
        headers=auth_headers(owner_token),
    )
    for i in range(3):
        await client.post(
            f"/api/projects/{project_id}/tasks",
            json={"title": f"T{i}", "assignee_id": member_id},
            headers=auth_headers(owner_token),
        )

    # 4, not 3: project_invite (from adding the member above) + 3x task_assigned.
    resp = await client.post("/api/notifications/read-all", headers=auth_headers(member_token))
    assert resp.json()["marked_read"] == 4

    unread = await client.get("/api/notifications/unread-count", headers=auth_headers(member_token))
    assert unread.json()["unread_count"] == 0


async def test_cannot_read_another_users_notification(client: AsyncClient):
    owner_token, _, project_id = await _setup_project(client)
    member_token, member_id = await register_and_login(client, "victim@example.com", "Victim")
    await client.post(
        f"/api/projects/{project_id}/members",
        json={"email": "victim@example.com", "role": "member"},
        headers=auth_headers(owner_token),
    )
    await client.post(
        f"/api/projects/{project_id}/tasks",
        json={"title": "T", "assignee_id": member_id},
        headers=auth_headers(owner_token),
    )
    notification_id = (
        await client.get("/api/notifications", headers=auth_headers(member_token))
    ).json()["items"][0]["id"]

    resp = await client.post(
        f"/api/notifications/{notification_id}/read", headers=auth_headers(owner_token)
    )
    assert resp.status_code == 404
