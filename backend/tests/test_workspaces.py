import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _register_and_login(client: AsyncClient, email: str, name: str) -> tuple[str, str]:
    await client.post(
        "/api/auth/register", json={"email": email, "password": "supersecret1", "full_name": name}
    )
    login = await client.post("/api/auth/login", json={"email": email, "password": "supersecret1"})
    token = login.json()["access_token"]
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    return token, me.json()["id"]


async def test_create_organization_seeds_owner_workspace(client: AsyncClient):
    token, _ = await _register_and_login(client, "owner@example.com", "Owner")
    headers = {"Authorization": f"Bearer {token}"}

    org_resp = await client.post("/api/organizations", json={"name": "Acme Inc"}, headers=headers)
    assert org_resp.status_code == 201
    org = org_resp.json()
    assert org["slug"] == "acme-inc"


async def test_create_workspace_and_list_members(client: AsyncClient):
    token, _ = await _register_and_login(client, "owner@example.com", "Owner")
    headers = {"Authorization": f"Bearer {token}"}

    org = (
        await client.post("/api/organizations", json={"name": "Acme"}, headers=headers)
    ).json()

    ws_resp = await client.post(
        f"/api/organizations/{org['id']}/workspaces",
        json={"name": "Engineering"},
        headers=headers,
    )
    assert ws_resp.status_code == 201
    workspace = ws_resp.json()

    members_resp = await client.get(
        f"/api/workspaces/{workspace['id']}/members", headers=headers
    )
    assert members_resp.status_code == 200
    members = members_resp.json()
    assert len(members) == 1
    assert members[0]["role"] == "owner"


async def test_non_member_cannot_list_workspace_members(client: AsyncClient):
    owner_token, _ = await _register_and_login(client, "owner@example.com", "Owner")
    outsider_token, _ = await _register_and_login(client, "outsider@example.com", "Outsider")

    org = (
        await client.post(
            "/api/organizations",
            json={"name": "Acme"},
            headers={"Authorization": f"Bearer {owner_token}"},
        )
    ).json()
    workspace = (
        await client.post(
            f"/api/organizations/{org['id']}/workspaces",
            json={"name": "Eng"},
            headers={"Authorization": f"Bearer {owner_token}"},
        )
    ).json()

    resp = await client.get(
        f"/api/workspaces/{workspace['id']}/members",
        headers={"Authorization": f"Bearer {outsider_token}"},
    )
    assert resp.status_code == 403


async def test_member_cannot_invite_but_admin_can(client: AsyncClient):
    owner_token, _ = await _register_and_login(client, "owner@example.com", "Owner")
    member_token, _ = await _register_and_login(client, "member@example.com", "Member")
    await _register_and_login(client, "invitee@example.com", "Invitee")

    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    org_resp = await client.post(
        "/api/organizations", json={"name": "Acme"}, headers=owner_headers
    )
    org = org_resp.json()
    workspace_resp = await client.post(
        f"/api/organizations/{org['id']}/workspaces",
        json={"name": "Eng"},
        headers=owner_headers,
    )
    workspace = workspace_resp.json()

    # Owner adds `member` as a plain MEMBER.
    add_resp = await client.post(
        f"/api/workspaces/{workspace['id']}/members",
        json={"email": "member@example.com", "role": "member"},
        headers=owner_headers,
    )
    assert add_resp.status_code == 201

    # A plain member cannot invite others.
    member_headers = {"Authorization": f"Bearer {member_token}"}
    forbidden_resp = await client.post(
        f"/api/workspaces/{workspace['id']}/members",
        json={"email": "invitee@example.com", "role": "member"},
        headers=member_headers,
    )
    assert forbidden_resp.status_code == 403

    # But the owner (>= admin) can invite the third user.
    invite_resp = await client.post(
        f"/api/workspaces/{workspace['id']}/members",
        json={"email": "invitee@example.com", "role": "admin"},
        headers=owner_headers,
    )
    assert invite_resp.status_code == 201
    assert invite_resp.json()["role"] == "admin"


async def test_list_organizations_includes_owned_and_invited(client: AsyncClient):
    owner_token, _ = await _register_and_login(client, "owner@example.com", "Owner")
    member_token, _ = await _register_and_login(client, "member@example.com", "Member")
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    org = (
        await client.post("/api/organizations", json={"name": "Acme"}, headers=owner_headers)
    ).json()
    # The owner's org auto-seeds a "General" workspace (see
    # organization_service.create_organization_with_owner) - invite the
    # member to that, which is what should surface the org for them.
    workspaces = (
        await client.get(f"/api/organizations/{org['id']}/workspaces", headers=owner_headers)
    ).json()
    general_workspace_id = workspaces[0]["id"]
    await client.post(
        f"/api/workspaces/{general_workspace_id}/members",
        json={"email": "member@example.com", "role": "member"},
        headers=owner_headers,
    )

    owner_orgs = (await client.get("/api/organizations", headers=owner_headers)).json()
    assert any(o["id"] == org["id"] for o in owner_orgs)

    member_headers = {"Authorization": f"Bearer {member_token}"}
    member_orgs = (await client.get("/api/organizations", headers=member_headers)).json()
    assert any(o["id"] == org["id"] for o in member_orgs)


async def test_list_organizations_excludes_orgs_user_has_no_access_to(client: AsyncClient):
    owner_token, _ = await _register_and_login(client, "owner@example.com", "Owner")
    outsider_token, _ = await _register_and_login(client, "outsider@example.com", "Outsider")

    await client.post(
        "/api/organizations",
        json={"name": "Acme"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    outsider_orgs = (
        await client.get(
            "/api/organizations", headers={"Authorization": f"Bearer {outsider_token}"}
        )
    ).json()
    assert outsider_orgs == []


async def test_list_workspaces_only_shows_workspaces_user_is_member_of(client: AsyncClient):
    owner_token, _ = await _register_and_login(client, "owner@example.com", "Owner")
    outsider_token, _ = await _register_and_login(client, "outsider@example.com", "Outsider")
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    org = (
        await client.post("/api/organizations", json={"name": "Acme"}, headers=owner_headers)
    ).json()
    await client.post(
        f"/api/organizations/{org['id']}/workspaces",
        json={"name": "Second Workspace"},
        headers=owner_headers,
    )

    owner_workspaces = (
        await client.get(f"/api/organizations/{org['id']}/workspaces", headers=owner_headers)
    ).json()
    # Owner sees both: the auto-seeded "General" workspace and the one just created.
    assert len(owner_workspaces) == 2

    outsider_workspaces = (
        await client.get(
            f"/api/organizations/{org['id']}/workspaces",
            headers={"Authorization": f"Bearer {outsider_token}"},
        )
    ).json()
    assert outsider_workspaces == []
