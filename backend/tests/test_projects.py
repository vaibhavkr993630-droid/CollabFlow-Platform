import pytest
from httpx import AsyncClient

from tests.helpers import auth_headers, create_org_and_workspace, register_and_login

pytestmark = pytest.mark.asyncio


async def test_create_project_seeds_creator_as_owner(client: AsyncClient):
    token, _ = await register_and_login(client, "owner@example.com", "Owner")
    _, workspace_id = await create_org_and_workspace(client, token, "Acme")

    resp = await client.post(
        f"/api/workspaces/{workspace_id}/projects",
        json={"name": "Website Revamp"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201
    project = resp.json()
    assert project["slug"] == "website-revamp"

    members = await client.get(
        f"/api/projects/{project['id']}/members", headers=auth_headers(token)
    )
    assert members.status_code == 200
    assert members.json()[0]["role"] == "owner"


async def test_workspace_outsider_cannot_create_project(client: AsyncClient):
    token, _ = await register_and_login(client, "owner@example.com", "Owner")
    outsider_token, _ = await register_and_login(client, "outsider@example.com", "Outsider")
    _, workspace_id = await create_org_and_workspace(client, token, "Acme")

    resp = await client.post(
        f"/api/workspaces/{workspace_id}/projects",
        json={"name": "Secret Project"},
        headers=auth_headers(outsider_token),
    )
    assert resp.status_code == 403


async def test_list_projects_in_workspace(client: AsyncClient):
    token, _ = await register_and_login(client, "owner@example.com", "Owner")
    _, workspace_id = await create_org_and_workspace(client, token, "Acme")

    await client.post(
        f"/api/workspaces/{workspace_id}/projects",
        json={"name": "Project A"},
        headers=auth_headers(token),
    )
    await client.post(
        f"/api/workspaces/{workspace_id}/projects",
        json={"name": "Project B"},
        headers=auth_headers(token),
    )

    resp = await client.get(
        f"/api/workspaces/{workspace_id}/projects", headers=auth_headers(token)
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 2


async def test_project_member_cannot_invite_but_admin_can(client: AsyncClient):
    owner_token, _ = await register_and_login(client, "owner@example.com", "Owner")
    member_token, _ = await register_and_login(client, "member@example.com", "Member")
    await register_and_login(client, "invitee@example.com", "Invitee")
    _, workspace_id = await create_org_and_workspace(client, owner_token, "Acme")

    project_resp = await client.post(
        f"/api/workspaces/{workspace_id}/projects",
        json={"name": "Project A"},
        headers=auth_headers(owner_token),
    )
    project_id = project_resp.json()["id"]

    add_resp = await client.post(
        f"/api/projects/{project_id}/members",
        json={"email": "member@example.com", "role": "member"},
        headers=auth_headers(owner_token),
    )
    assert add_resp.status_code == 201

    forbidden = await client.post(
        f"/api/projects/{project_id}/members",
        json={"email": "invitee@example.com", "role": "member"},
        headers=auth_headers(member_token),
    )
    assert forbidden.status_code == 403

    allowed = await client.post(
        f"/api/projects/{project_id}/members",
        json={"email": "invitee@example.com", "role": "admin"},
        headers=auth_headers(owner_token),
    )
    assert allowed.status_code == 201
