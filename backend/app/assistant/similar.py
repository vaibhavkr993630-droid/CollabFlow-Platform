"""Finds tasks by meaning, using the searchable copies kept by app/assistant/indexing.py."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.client import AssistantClient
from app.models.comment import Comment
from app.models.search_document import SearchDocument
from app.models.task import Task
from app.models.user import User
from app.schemas.assistant import SimilarTask

# Similarity runs from 0 to 1. Measured on the sample project (2026-11-21, gemini-embedding-001
# at 768 dims): the right answer scored 0.73-0.74, an unrelated query's best was 0.52, true
# duplicate titles scored 0.82-0.84 and different tasks at most 0.65.
SEARCH_MIN_SIMILARITY = 0.60
# Search also drops results far below the best one, so a strong match is not followed by a tail
# of loosely related tasks.
SEARCH_MAX_GAP_FROM_BEST = 0.12
DUPLICATE_MIN_SIMILARITY = 0.75
MAX_SNIPPET_CHARS = 160


async def find_similar_tasks(
    db: AsyncSession,
    client: AssistantClient,
    *,
    project_id: uuid.UUID,
    query: str,
    min_similarity: float,
    limit: int,
    max_gap_from_best: float | None = None,
) -> list[SimilarTask]:
    [query_vector] = await client.embed([query])

    distance = SearchDocument.embedding.cosine_distance(query_vector)
    # A subtask or a comment surfaces its top-level task, which is what the board shows.
    top_task_id = func.coalesce(Task.parent_task_id, Task.id)
    best_per_task = (
        select(
            top_task_id.label("task_id"),
            distance.label("distance"),
            SearchDocument.content,
            SearchDocument.comment_id,
        )
        .join(Task, Task.id == SearchDocument.task_id)
        # The project filter comes first and is part of the same query, so another
        # project's text can never be ranked, returned, or leak through a snippet.
        .where(SearchDocument.project_id == project_id)
        .distinct(top_task_id)
        .order_by(top_task_id, distance)
        .subquery()
    )
    rows = (
        await db.execute(
            select(best_per_task, Task, Comment.body, User.full_name)
            .join(Task, Task.id == best_per_task.c.task_id)
            .outerjoin(Comment, Comment.id == best_per_task.c.comment_id)
            .outerjoin(User, User.id == Comment.author_id)
            .where(best_per_task.c.distance <= 1 - min_similarity)
            .order_by(best_per_task.c.distance)
            .limit(limit)
        )
    ).all()

    if max_gap_from_best is not None and rows:
        best_distance = rows[0].distance
        rows = [r for r in rows if r.distance - best_distance <= max_gap_from_best]

    return [
        SimilarTask(
            id=row.Task.id,
            title=row.Task.title,
            status=row.Task.status,
            priority=row.Task.priority,
            similarity=round(1 - row.distance, 3),
            matched_in="comment" if row.comment_id else "task",
            # Readable on its own next to the title: "Priya Sharma: <comment>" for a comment,
            # the description for a task (the title is already shown).
            matched_text=_snippet(
                f"{row.full_name}: {row.body}"
                if row.comment_id
                else (row.Task.description or row.Task.title)
            ),
        )
        for row in rows
    ]


def _snippet(content: str) -> str:
    text = " ".join(content.split())
    return text if len(text) <= MAX_SNIPPET_CHARS else text[: MAX_SNIPPET_CHARS - 1] + "…"
