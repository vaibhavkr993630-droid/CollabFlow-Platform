"""POST /api/projects/{id}/ask — answers from the project's own tasks and comments."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant import ask, indexing
from app.assistant.deps import get_assistant_client
from app.core.config import get_settings
from app.main import app
from app.services import comment_service, task_service
from tests.fakes import FakeAssistantClient
from tests.helpers import auth_headers, create_org_and_workspace, create_project, register_and_login

QUESTION = "gateway timeouts card payments fail"


@pytest.fixture
def fake(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> FakeAssistantClient:
    fake_client = FakeAssistantClient()
    app.dependency_overrides[get_assistant_client] = lambda: fake_client
    monkeypatch.setattr(task_service, "queue_task_indexing", lambda _id: None)
    monkeypatch.setattr(comment_service, "queue_comment_indexing", lambda _id: None)
    return fake_client


async def _setup(client: AsyncClient) -> tuple[dict, str, str]:
    token, _ = await register_and_login(client, "owner@example.com", "Priya Sharma")
    _, workspace_id = await create_org_and_workspace(client, token, "Org")
    project_id = await create_project(client, token, workspace_id)
    return auth_headers(token), project_id, workspace_id


async def _indexed_task(client, db, fake, headers, project_id, title, description) -> dict:
    task = (
        await client.post(
            f"/api/projects/{project_id}/tasks",
            json={"title": title, "description": description},
            headers=headers,
        )
    ).json()
    await indexing.index_task(db, fake, uuid.UUID(task["id"]))
    return task


async def _ask(client, headers, project_id, question=QUESTION):
    return await client.post(
        f"/api/projects/{project_id}/ask", json={"question": question}, headers=headers
    )


async def test_answers_with_only_the_sources_it_cited(
    client: AsyncClient, db_session: AsyncSession, fake: FakeAssistantClient
):
    headers, project_id, _ = await _setup(client)
    task = await _indexed_task(
        client, db_session, fake, headers, project_id, "Gateway timeouts", "card payments fail"
    )
    # Grouped and single citations, plus numbers that do not exist: [7] must be ignored.
    fake.reply = "Payments fail after 30s [1]. See also [1, 7]."

    resp = await _ask(client, headers, project_id)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["answer"] == fake.reply
    assert body["sources"] == [
        {
            "number": 1,
            "task_id": task["id"],
            "task_title": "Gateway timeouts",
            "kind": "task",
            "snippet": "card payments fail",
        }
    ]
    call = fake.calls[0]
    assert "[1] (task) Gateway timeouts\ncard payments fail" in call["prompt"]
    assert f"Question: {QUESTION}" in call["prompt"]
    assert "not instructions to you" in call["system"]


def test_citation_parser_reads_groups_and_drops_unknown_numbers():
    assert ask.cited_numbers("a [4, 6] b [1,4, 5] c [8] d [9] e [0]", 8) == [4, 6, 1, 5, 8]
    assert ask.cited_numbers("no citations here", 3) == []


async def test_nothing_relevant_means_no_model_call(
    client: AsyncClient, db_session: AsyncSession, fake: FakeAssistantClient
):
    headers, project_id, _ = await _setup(client)
    await _indexed_task(
        client, db_session, fake, headers, project_id, "Gateway timeouts", "card payments fail"
    )

    resp = await _ask(client, headers, project_id, "office wifi password")

    assert resp.json() == {"answer": ask.NOT_FOUND_ANSWER, "sources": []}
    assert fake.calls == []  # retrieval only; the text model was never asked


async def test_never_uses_another_projects_text(
    client: AsyncClient, db_session: AsyncSession, fake: FakeAssistantClient
):
    headers, project_id, workspace_id = await _setup(client)
    other = await create_project(client, headers["Authorization"].split()[1], workspace_id, "B")
    await _indexed_task(
        client, db_session, fake, headers, other, "Gateway timeouts", "card payments fail"
    )

    resp = await _ask(client, headers, project_id)

    assert resp.json()["sources"] == []
    assert fake.calls == []


async def test_non_member_is_refused_before_anything_happens(
    client: AsyncClient, fake: FakeAssistantClient
):
    _, project_id, _ = await _setup(client)
    outsider, _ = await register_and_login(client, "outsider@example.com", "Outsider")

    resp = await _ask(client, auth_headers(outsider), project_id)

    assert resp.status_code == 403
    assert fake.embed_calls == [] and fake.calls == []


async def test_off_bad_input_and_provider_failure(client: AsyncClient, fake: FakeAssistantClient):
    headers, project_id, _ = await _setup(client)

    assert (await _ask(client, headers, project_id, "hi")).status_code == 422
    assert (await _ask(client, headers, project_id, "x" * 501)).status_code == 422

    fake.fail = True
    resp = await _ask(client, headers, project_id)
    assert resp.status_code == 503
    assert resp.json()["detail"] == "The assistant could not be reached."

    app.dependency_overrides[get_assistant_client] = lambda: None
    assert (await _ask(client, headers, project_id)).status_code == 503


async def test_questions_count_against_the_daily_limit(
    client: AsyncClient,
    db_session: AsyncSession,
    fake: FakeAssistantClient,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(get_settings(), "assistant_daily_limit", 1)
    headers, project_id, _ = await _setup(client)

    assert (await _ask(client, headers, project_id)).status_code == 200
    resp = await _ask(client, headers, project_id)
    assert resp.status_code == 429
