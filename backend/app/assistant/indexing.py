"""
Keeps `search_documents` in step with tasks and comments.

Runs only in background jobs (app/workers/tasks.py), never inside a user's request: the
provider can be slow or down, and saving a task must never wait for it or fail because of it.
Text that has not changed is never sent to the provider again (content hash), so dragging a
card between columns costs nothing.
"""

import hashlib
import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import and_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from app.assistant.client import AssistantClient
from app.core.config import get_settings
from app.models.comment import Comment
from app.models.search_document import SearchDocument
from app.models.task import Task

logger = logging.getLogger(__name__)

# Items per embedding request: fewer requests keeps the free tier's per-minute limit happy.
BATCH_SIZE = 50
# Upper bound per re-index run, so one run cannot use the whole daily quota.
REINDEX_LIMIT = 200


@dataclass
class _Source:
    key: str
    project_id: uuid.UUID
    task_id: uuid.UUID
    comment_id: uuid.UUID | None
    content: str


def task_content(task: Task) -> str:
    return f"{task.title}\n{task.description or ''}".strip()


def comment_content(comment: Comment, task: Task) -> str:
    # The task title gives a short comment ("works now") the context it needs to be found.
    return f"Comment by {comment.author.full_name} on '{task.title}': {comment.body}"


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


async def is_ready(db: AsyncSession) -> bool:
    """False when the database has no pgvector (the migration then skipped the table)."""
    return bool(await db.scalar(text("SELECT to_regclass('public.search_documents') IS NOT NULL")))


async def _index(db: AsyncSession, client: AssistantClient, sources: list[_Source]) -> int:
    """Embeds and stores the given sources. Returns how many were sent to the provider."""
    if not sources:
        return 0
    model = get_settings().assistant_embedding_model
    existing = {
        doc.source_key: doc
        for doc in (
            await db.execute(
                select(SearchDocument).where(
                    SearchDocument.source_key.in_([s.key for s in sources])
                )
            )
        ).scalars()
    }

    changed: list[_Source] = []
    for source in sources:
        doc = existing.get(source.key)
        if doc and doc.content_hash == _hash(source.content) and doc.embedding_model == model:
            # Unchanged text: only mark it as checked, so the re-index job skips it next time.
            doc.updated_at = text("now()")
        else:
            changed.append(source)

    for start in range(0, len(changed), BATCH_SIZE):
        batch = changed[start : start + BATCH_SIZE]
        vectors = await client.embed([s.content for s in batch])
        for source, vector in zip(batch, vectors, strict=True):
            values = {
                "source_key": source.key,
                "project_id": source.project_id,
                "task_id": source.task_id,
                "comment_id": source.comment_id,
                "content": source.content,
                "content_hash": _hash(source.content),
                "embedding": vector,
                "embedding_model": model,
            }
            update = {k: v for k, v in values.items() if k != "source_key"}
            await db.execute(
                insert(SearchDocument)
                .values(id=uuid.uuid4(), **values)
                .on_conflict_do_update(
                    index_elements=["source_key"], set_={**update, "updated_at": text("now()")}
                )
            )
    await db.commit()
    return len(changed)


def _task_source(task: Task) -> _Source:
    return _Source(f"task:{task.id}", task.project_id, task.id, None, task_content(task))


def _comment_source(comment: Comment) -> _Source:
    task = comment.task
    return _Source(
        f"comment:{comment.id}",
        task.project_id,
        task.id,
        comment.id,
        comment_content(comment, task),
    )


async def index_task(db: AsyncSession, client: AssistantClient, task_id: uuid.UUID) -> int:
    task = await db.get(Task, task_id)
    if task is None:  # deleted before the job ran; its rows went with it (ON DELETE CASCADE)
        return 0
    return await _index(db, client, [_task_source(task)])


async def index_comment(db: AsyncSession, client: AssistantClient, comment_id: uuid.UUID) -> int:
    comment = await db.scalar(
        select(Comment)
        .options(selectinload(Comment.author), selectinload(Comment.task))
        .where(Comment.id == comment_id)
    )
    if comment is None:
        return 0
    return await _index(db, client, [_comment_source(comment)])


async def reindex_stale(
    db: AsyncSession, client: AssistantClient, *, limit: int = REINDEX_LIMIT
) -> int:
    """
    Catches up on anything the per-change jobs missed (a worker that was down, a provider
    outage, data created before this feature existed). Picks tasks and comments that have no
    searchable copy yet, or whose task changed after the copy was made. Unchanged text is
    detected by hash and not re-sent, so a re-check costs one cheap query per row.
    """
    task_doc = aliased(SearchDocument)
    stale_tasks = (
        await db.execute(
            select(Task)
            .outerjoin(
                task_doc, and_(task_doc.task_id == Task.id, task_doc.comment_id.is_(None))
            )
            .where((task_doc.id.is_(None)) | (Task.updated_at > task_doc.updated_at))
            .limit(limit)
        )
    ).scalars().all()

    comment_doc = aliased(SearchDocument)
    stale_comments = (
        await db.execute(
            select(Comment)
            .join(Task, Task.id == Comment.task_id)
            .outerjoin(comment_doc, comment_doc.comment_id == Comment.id)
            .options(selectinload(Comment.author), selectinload(Comment.task))
            .where((comment_doc.id.is_(None)) | (Task.updated_at > comment_doc.updated_at))
            .limit(limit)
        )
    ).scalars().all()

    sources = [_task_source(t) for t in stale_tasks] + [
        _comment_source(c) for c in stale_comments
    ]
    return await _index(db, client, sources[:limit])
