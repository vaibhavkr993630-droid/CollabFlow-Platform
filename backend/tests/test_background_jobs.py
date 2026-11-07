"""
Background jobs run the way a real Celery worker runs them: plain sync functions, called
one after another in the same process. These tests are deliberately sync (no `async def`),
because each job enters async code through its own asyncio.run().
"""

import asyncio
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.models.notification import Notification, NotificationType
from app.models.organization import Organization
from app.models.project import Project
from app.models.task import Task, TaskStatus
from app.models.user import User
from app.models.workspace import Workspace
from app.workers.tasks import send_due_soon_reminders

settings = get_settings()


def _run(coro_fn):
    """Runs one async helper on its own engine and loop, like a job would."""

    async def _wrapper():
        engine = create_async_engine(settings.test_database_url, poolclass=NullPool)
        try:
            session_factory = async_sessionmaker(
                bind=engine, class_=AsyncSession, expire_on_commit=False
            )
            async with session_factory() as db:
                return await coro_fn(db)
        finally:
            await engine.dispose()

    return asyncio.run(_wrapper())


async def _seed_task_due_tomorrow(db: AsyncSession) -> uuid.UUID:
    user = User(email="due@example.com", hashed_password="x", full_name="Due Soon")
    db.add(user)
    await db.flush()
    org = Organization(name="Org", slug=f"org-{uuid.uuid4().hex[:8]}", owner_id=user.id)
    db.add(org)
    await db.flush()
    workspace = Workspace(name="Eng", slug="eng", organization_id=org.id)
    db.add(workspace)
    await db.flush()
    project = Project(name="Launch", slug="launch", workspace_id=workspace.id)
    db.add(project)
    await db.flush()
    db.add(
        Task(
            project_id=project.id,
            title="Ship it",
            status=TaskStatus.TODO,
            assignee_id=user.id,
            due_date=date.today() + timedelta(days=1),
            created_by_id=user.id,
        )
    )
    await db.commit()
    return user.id


@pytest.fixture
def jobs_use_test_database(monkeypatch: pytest.MonkeyPatch) -> None:
    # Background jobs build their own engine from settings.database_url; point it at the
    # test database for the duration of one test.
    monkeypatch.setattr(settings, "database_url", settings.test_database_url)


def test_due_soon_job_runs_twice_in_one_process(jobs_use_test_database: None) -> None:
    """
    Regression test: the second job in the same process used to crash with "attached to a
    different loop", because pooled DB connections and the cached Redis client outlived the
    event loop of the first job.
    """
    user_id = _run(_seed_task_due_tomorrow)

    send_due_soon_reminders()
    send_due_soon_reminders()

    async def _count(db: AsyncSession) -> int:
        return await db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.type == NotificationType.TASK_DUE_SOON,
            )
        )

    # One reminder per run: both runs reached the database and Redis successfully.
    assert _run(_count) == 2
