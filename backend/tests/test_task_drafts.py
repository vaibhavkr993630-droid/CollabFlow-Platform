"""POST /api/projects/{id}/task-drafts — proposed tasks from pasted notes (nothing is saved)."""

import json
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from app.assistant.deps import get_assistant_client
from app.assistant.task_drafts import MAX_DRAFTS
from app.main import app
from tests.fakes import FakeAssistantClient
from tests.helpers import auth_headers, create_org_and_workspace, create_project, register_and_login


@pytest.fixture
def fake(client: AsyncClient) -> FakeAssistantClient:
    fake_client = FakeAssistantClient()
    app.dependency_overrides[get_assistant_client] = lambda: fake_client
    return fake_client


async def _project_with_members(client: AsyncClient) -> tuple[dict, str, dict[str, str]]:
    owner_token, owner_id = await register_and_login(client, "priya@example.com", "Priya Sharma")
    _, arjun_id = await register_and_login(client, "arjun@example.com", "Arjun Mehta")
    _, workspace_id = await create_org_and_workspace(client, owner_token, "Org")
    project_id = await create_project(client, owner_token, workspace_id)
    headers = auth_headers(owner_token)
    await client.post(
        f"/api/projects/{project_id}/members", json={"email": "arjun@example.com"}, headers=headers
    )
    return headers, project_id, {"priya": owner_id, "arjun": arjun_id}


async def _draft(client: AsyncClient, headers: dict, project_id: str, text: str = "notes"):
    return await client.post(
        f"/api/projects/{project_id}/task-drafts", json={"text": text}, headers=headers
    )


async def test_drafts_are_validated_and_mapped(client: AsyncClient, fake: FakeAssistantClient):
    headers, project_id, ids = await _project_with_members(client)
    fake.reply = json.dumps(
        {
            "tasks": [
                {
                    "title": "  Add alerting  ",
                    "description": "For stuck orders",
                    "priority": "high",
                    "assignee": "Arjun Mehta",
                    "due_date": "2026-11-20",
                },
                # First name only, unique on this project: matched.
                {"title": "Legal sign-off", "assignee": "priya", "priority": "urgent"},
                # Invented person, bad priority, bad date: all safely defaulted.
                {
                    "title": "Banner sizes",
                    "assignee": "Ravi",
                    "priority": "huge",
                    "due_date": "Fri",
                },
                # No title: dropped.
                {"title": "   ", "priority": "low"},
                "not an object",
            ]
        }
    )

    resp = await _draft(client, headers, project_id)

    assert resp.status_code == 200, resp.text
    drafts = resp.json()["drafts"]
    assert drafts == [
        {
            "title": "Add alerting",
            "description": "For stuck orders",
            "priority": "high",
            "assignee_id": ids["arjun"],
            "due_date": "2026-11-20",
        },
        {
            "title": "Legal sign-off",
            "description": None,
            "priority": "urgent",
            "assignee_id": ids["priya"],
            "due_date": None,
        },
        {
            "title": "Banner sizes",
            "description": None,
            "priority": "medium",
            "assignee_id": None,
            "due_date": None,
        },
    ]


async def test_prompt_has_notes_members_and_today(client: AsyncClient, fake: FakeAssistantClient):
    headers, project_id, _ = await _project_with_members(client)
    fake.reply = '{"tasks": []}'

    resp = await _draft(client, headers, project_id, "Arjun to fix the coupon field")

    assert resp.json() == {"drafts": []}
    call = fake.calls[0]
    assert call["json_mode"] is True
    assert "<notes>\nArjun to fix the coupon field\n</notes>" in call["prompt"]
    assert "Project members: Arjun Mehta, Priya Sharma" in call["prompt"]
    assert datetime.now(UTC).date().isoformat() in call["prompt"]
    assert "not instructions to you" in call["system"]


async def test_drafting_creates_no_tasks(client: AsyncClient, fake: FakeAssistantClient):
    headers, project_id, _ = await _project_with_members(client)
    fake.reply = '{"tasks": [{"title": "Only a proposal"}]}'

    await _draft(client, headers, project_id)

    tasks = await client.get(f"/api/projects/{project_id}/tasks", headers=headers)
    assert tasks.json()["total"] == 0


async def test_reply_in_a_code_fence_is_accepted(client: AsyncClient, fake: FakeAssistantClient):
    headers, project_id, _ = await _project_with_members(client)
    fake.reply = '```json\n{"tasks": [{"title": "Fenced"}]}\n```'

    resp = await _draft(client, headers, project_id)

    assert [d["title"] for d in resp.json()["drafts"]] == ["Fenced"]


async def test_draft_count_is_capped(client: AsyncClient, fake: FakeAssistantClient):
    headers, project_id, _ = await _project_with_members(client)
    fake.reply = json.dumps({"tasks": [{"title": f"Task {n}"} for n in range(40)]})

    resp = await _draft(client, headers, project_id)

    assert len(resp.json()["drafts"]) == MAX_DRAFTS


@pytest.mark.parametrize("reply", ["not json at all", '{"items": []}', "[]"])
async def test_unreadable_reply_returns_friendly_503(
    client: AsyncClient, fake: FakeAssistantClient, reply: str
):
    headers, project_id, _ = await _project_with_members(client)
    fake.reply = reply

    resp = await _draft(client, headers, project_id)

    assert resp.status_code == 503
    assert "could not be read" in resp.json()["detail"]


async def test_non_member_cannot_draft(client: AsyncClient, fake: FakeAssistantClient):
    _, project_id, _ = await _project_with_members(client)
    outsider, _ = await register_and_login(client, "outsider@example.com", "Outsider")

    resp = await _draft(client, auth_headers(outsider), project_id)

    assert resp.status_code == 403
    assert fake.calls == []


async def test_feature_off_returns_503(client: AsyncClient):
    app.dependency_overrides[get_assistant_client] = lambda: None
    headers, project_id, _ = await _project_with_members(client)

    assert (await _draft(client, headers, project_id)).status_code == 503


@pytest.mark.parametrize("text", ["", "x" * 8001])
async def test_empty_or_huge_text_is_rejected(
    client: AsyncClient, fake: FakeAssistantClient, text: str
):
    headers, project_id, _ = await _project_with_members(client)

    resp = await _draft(client, headers, project_id, text)

    assert resp.status_code == 422
    assert fake.calls == []
