"""Searchable copies of tasks and comments: created, kept current, removed with their source."""

import asyncio
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.assistant import deps, indexing
from app.core.config import get_settings
from app.models.search_document import EMBEDDING_DIMENSIONS, SearchDocument
from app.services import comment_service, task_service
from app.workers.tasks import index_task_text
from tests.fakes import FakeAssistantClient
from tests.helpers import auth_headers, create_org_and_workspace, create_project, register_and_login

settings = get_settings()


@pytest.fixture
def queued(monkeypatch: pytest.MonkeyPatch) -> dict[str, list]:
    """Records what the services queue for indexing, instead of sending it to Celery."""
    calls: dict[str, list] = {"tasks": [], "comments": []}
    monkeypatch.setattr(task_service, "queue_task_indexing", calls["tasks"].append)
    monkeypatch.setattr(comment_service, "queue_comment_indexing", calls["comments"].append)
    return calls


async def _project_with_task(client: AsyncClient) -> tuple[dict, str, dict]:
    token, _ = await register_and_login(client, "owner@example.com", "Priya Sharma")
    _, workspace_id = await create_org_and_workspace(client, token, "Org")
    project_id = await create_project(client, token, workspace_id)
    headers = auth_headers(token)
    task = (
        await client.post(
            f"/api/projects/{project_id}/tasks",
            json={"title": "Gateway timeouts", "description": "Card payments fail"},
            headers=headers,
        )
    ).json()
    return headers, project_id, task


async def _docs(db: AsyncSession) -> list[SearchDocument]:
    db.expire_all()
    return list((await db.execute(select(SearchDocument))).scalars())


async def test_database_is_ready_for_vectors(db_session: AsyncSession):
    assert await indexing.is_ready(db_session) is True


async def test_index_task_stores_a_searchable_copy(
    client: AsyncClient, db_session: AsyncSession, queued
):
    _, project_id, task = await _project_with_task(client)
    fake = FakeAssistantClient()

    sent = await indexing.index_task(db_session, fake, uuid.UUID(task["id"]))

    assert sent == 1
    [doc] = await _docs(db_session)
    assert doc.source_key == f"task:{task['id']}"
    assert str(doc.project_id) == project_id
    assert doc.comment_id is None
    assert doc.content == "Gateway timeouts\nCard payments fail"
    assert doc.embedding_model == settings.assistant_embedding_model
    assert len(doc.embedding) == EMBEDDING_DIMENSIONS


async def test_unchanged_text_is_not_sent_again(
    client: AsyncClient, db_session: AsyncSession, queued
):
    headers, _, task = await _project_with_task(client)
    fake = FakeAssistantClient()
    await indexing.index_task(db_session, fake, uuid.UUID(task["id"]))

    # A status change does not change the searchable text.
    await client.patch(f"/api/tasks/{task['id']}", json={"status": "done"}, headers=headers)
    assert await indexing.index_task(db_session, fake, uuid.UUID(task["id"])) == 0

    await client.patch(
        f"/api/tasks/{task['id']}", json={"title": "Gateway outage"}, headers=headers
    )
    db_session.expire_all()
    assert await indexing.index_task(db_session, fake, uuid.UUID(task["id"])) == 1
    [doc] = await _docs(db_session)
    assert doc.content.startswith("Gateway outage")
    assert len(fake.embed_calls) == 2


async def test_comment_copy_carries_author_and_task_title(
    client: AsyncClient, db_session: AsyncSession, queued
):
    headers, _, task = await _project_with_task(client)
    comment = (
        await client.post(
            f"/api/tasks/{task['id']}/comments",
            json={"body": "Raised the timeout"},
            headers=headers,
        )
    ).json()

    await indexing.index_comment(db_session, FakeAssistantClient(), uuid.UUID(comment["id"]))

    [doc] = await _docs(db_session)
    assert doc.source_key == f"comment:{comment['id']}"
    assert str(doc.task_id) == task["id"]
    assert doc.content == "Comment by Priya Sharma on 'Gateway timeouts': Raised the timeout"


async def test_deleting_a_task_removes_its_copies(
    client: AsyncClient, db_session: AsyncSession, queued
):
    headers, _, task = await _project_with_task(client)
    comment = (
        await client.post(f"/api/tasks/{task['id']}/comments", json={"body": "x"}, headers=headers)
    ).json()
    fake = FakeAssistantClient()
    await indexing.index_task(db_session, fake, uuid.UUID(task["id"]))
    await indexing.index_comment(db_session, fake, uuid.UUID(comment["id"]))
    assert len(await _docs(db_session)) == 2

    resp = await client.delete(f"/api/tasks/{task['id']}", headers=headers)

    assert resp.status_code == 204
    assert await _docs(db_session) == []


async def test_reindex_catches_up_in_batches_and_then_has_nothing_to_do(
    client: AsyncClient, db_session: AsyncSession, queued
):
    headers, project_id, task = await _project_with_task(client)
    await client.post(
        f"/api/projects/{project_id}/tasks", json={"title": "Second task"}, headers=headers
    )
    await client.post(f"/api/tasks/{task['id']}/comments", json={"body": "hi"}, headers=headers)
    fake = FakeAssistantClient()

    assert await indexing.reindex_stale(db_session, fake) == 3
    assert len(fake.embed_calls) == 1  # all three in one request

    assert await indexing.reindex_stale(db_session, fake) == 0

    # A status-only change marks the task as changed but costs no provider call.
    await client.patch(f"/api/tasks/{task['id']}", json={"status": "done"}, headers=headers)
    assert await indexing.reindex_stale(db_session, fake) == 0
    assert len(fake.embed_calls) == 1


async def test_provider_failure_stores_nothing(
    client: AsyncClient, db_session: AsyncSession, queued
):
    _, _, task = await _project_with_task(client)

    with pytest.raises(Exception, match="could not be reached"):
        await indexing.index_task(db_session, FakeAssistantClient(fail=True), uuid.UUID(task["id"]))
    await db_session.rollback()
    assert await _docs(db_session) == []


async def test_services_queue_indexing_only_when_text_changes(client: AsyncClient, queued):
    headers, _, task = await _project_with_task(client)
    assert [str(t) for t in queued["tasks"]] == [task["id"]]

    await client.patch(f"/api/tasks/{task['id']}", json={"status": "done"}, headers=headers)
    await client.patch(f"/api/tasks/{task['id']}", json={"priority": "high"}, headers=headers)
    assert len(queued["tasks"]) == 1

    await client.patch(f"/api/tasks/{task['id']}", json={"description": "New"}, headers=headers)
    assert len(queued["tasks"]) == 2

    comment = (
        await client.post(f"/api/tasks/{task['id']}/comments", json={"body": "x"}, headers=headers)
    ).json()
    assert [str(c) for c in queued["comments"]] == [comment["id"]]


def test_worker_job_indexes_and_runs_twice_in_one_process(
    monkeypatch: pytest.MonkeyPatch, client: AsyncClient
):
    """The real Celery job body, run the way a worker runs it (task 1's event-loop fix)."""
    monkeypatch.setattr(settings, "database_url", settings.test_database_url)
    fake = FakeAssistantClient()
    monkeypatch.setattr(deps, "get_assistant_client", lambda: fake)

    async def seed_task() -> str:
        from app.models.task import Task
        from tests.test_background_jobs import _seed_task_due_tomorrow

        engine = create_async_engine(settings.test_database_url, poolclass=NullPool)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as db:
                await _seed_task_due_tomorrow(db)
                return str(await db.scalar(select(Task.id)))
        finally:
            await engine.dispose()

    task_id = asyncio.run(seed_task())

    assert index_task_text(task_id) == 1
    assert index_task_text(task_id) == 0  # second job, same process: no crash, nothing to send
