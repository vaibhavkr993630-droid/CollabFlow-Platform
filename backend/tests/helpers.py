from httpx import AsyncClient


async def register_and_login(client: AsyncClient, email: str, name: str) -> tuple[str, str]:
    """Registers + logs in a user, returning (access_token, user_id)."""
    await client.post(
        "/api/auth/register", json={"email": email, "password": "supersecret1", "full_name": name}
    )
    login = await client.post("/api/auth/login", json={"email": email, "password": "supersecret1"})
    token = login.json()["access_token"]
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    return token, me.json()["id"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def create_org_and_workspace(
    client: AsyncClient, token: str, org_name: str
) -> tuple[str, str]:
    """Creates an org (which auto-seeds a 'General' workspace) as `token`'s user, returning
    (organization_id, workspace_id)."""
    headers = auth_headers(token)
    org = (await client.post("/api/organizations", json={"name": org_name}, headers=headers)).json()
    ws_resp = await client.post(
        f"/api/organizations/{org['id']}/workspaces", json={"name": "Eng"}, headers=headers
    )
    workspace = ws_resp.json()
    return org["id"], workspace["id"]


async def create_project(
    client: AsyncClient, token: str, workspace_id: str, name: str = "Project X"
) -> str:
    """Creates a project in the given workspace as `token`'s user, returning project_id."""
    resp = await client.post(
        f"/api/workspaces/{workspace_id}/projects",
        json={"name": name},
        headers=auth_headers(token),
    )
    return resp.json()["id"]
