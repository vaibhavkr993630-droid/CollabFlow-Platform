"""Task search: titles, descriptions, comments and subtasks, scoped to one project."""

from httpx import AsyncClient

from tests.helpers import auth_headers, create_org_and_workspace, create_project, register_and_login


async def _setup(client: AsyncClient) -> tuple[dict[str, str], str, str]:
    token, _ = await register_and_login(client, "search@example.com", "Searcher")
    _, workspace_id = await create_org_and_workspace(client, token, "Search Org")
    project_id = await create_project(client, token, workspace_id)
    return auth_headers(token), project_id, workspace_id


async def _task(client, headers, project_id, **fields) -> dict:
    resp = await client.post(f"/api/projects/{project_id}/tasks", json=fields, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _search(client, headers, project_id, text) -> list[str]:
    resp = await client.get(
        f"/api/projects/{project_id}/tasks", params={"search": text}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    return sorted(item["title"] for item in resp.json()["items"])


async def test_search_matches_description(client: AsyncClient):
    headers, project_id, _ = await _setup(client)
    await _task(client, headers, project_id, title="Release", description="Rotate the API keys")
    await _task(client, headers, project_id, title="Docs", description="Write the guide")

    assert await _search(client, headers, project_id, "keys") == ["Release"]


async def test_search_matches_word_forms(client: AsyncClient):
    headers, project_id, _ = await _setup(client)
    await _task(client, headers, project_id, title="Ops", description="Deploy the build tonight")

    assert await _search(client, headers, project_id, "deploying") == ["Ops"]


async def test_search_matches_comment_text(client: AsyncClient):
    headers, project_id, _ = await _setup(client)
    task = await _task(client, headers, project_id, title="Checkout page")
    await _task(client, headers, project_id, title="Profile page")
    await client.post(
        f"/api/tasks/{task['id']}/comments",
        json={"body": "The payment gateway times out"},
        headers=headers,
    )

    assert await _search(client, headers, project_id, "gateway") == ["Checkout page"]


async def test_search_on_subtask_returns_its_parent(client: AsyncClient):
    headers, project_id, _ = await _setup(client)
    parent = await _task(client, headers, project_id, title="Mobile app")
    child = await _task(
        client, headers, project_id, title="Push notifications", parent_task_id=parent["id"]
    )
    await client.post(
        f"/api/tasks/{child['id']}/comments", json={"body": "Use Firebase"}, headers=headers
    )

    # The board lists top-level tasks only, so a subtask hit shows its parent.
    assert await _search(client, headers, project_id, "notifications") == ["Mobile app"]
    assert await _search(client, headers, project_id, "firebase") == ["Mobile app"]


async def test_search_keeps_partial_title_matching(client: AsyncClient):
    headers, project_id, _ = await _setup(client)
    await _task(client, headers, project_id, title="Fix login bug")

    assert await _search(client, headers, project_id, "log") == ["Fix login bug"]


async def test_search_treats_wildcards_literally(client: AsyncClient):
    headers, project_id, _ = await _setup(client)
    await _task(client, headers, project_id, title="Fix login bug")
    await _task(client, headers, project_id, title="Raise limit to 100%")

    assert await _search(client, headers, project_id, "%") == ["Raise limit to 100%"]
    assert await _search(client, headers, project_id, "_") == []


async def test_search_never_returns_other_projects(client: AsyncClient):
    headers, project_id, workspace_id = await _setup(client)
    token = headers["Authorization"].split()[1]
    other_project = await create_project(client, token, workspace_id, "Other")
    await _task(client, headers, other_project, title="Secret", description="quarterly budget")
    await _task(client, headers, project_id, title="Mine", description="team offsite")

    assert await _search(client, headers, project_id, "budget") == []
    assert await _search(client, headers, other_project, "budget") == ["Secret"]
