import uuid
from datetime import date

from sqlalchemy import ColumnElement, exists, func, literal_column, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.comment import Comment
from app.models.label import task_labels
from app.models.task import SortOrder, Task, TaskPriority, TaskSortField, TaskStatus

_SORT_COLUMNS = {
    TaskSortField.CREATED_AT: Task.created_at,
    TaskSortField.DUE_DATE: Task.due_date,
    TaskSortField.PRIORITY: Task.priority,
    TaskSortField.STATUS: Task.status,
    TaskSortField.POSITION: Task.position,
    TaskSortField.TITLE: Task.title,
}

# Search uses Postgres full-text search with the 'english' configuration, so word forms
# match ("deploying" finds "deploy"). _comment_document must stay identical to the GIN
# index in migration a7c3e9d41b20, otherwise Postgres cannot use it. Literal SQL (not
# bound parameters) keeps the expressions equal.
_TS_CONFIG = literal_column("'english'")


def _task_document(task) -> ColumnElement:
    text = task.title.op("||")(literal_column("' '")).op("||")(
        func.coalesce(task.description, literal_column("''"))
    )
    return func.to_tsvector(_TS_CONFIG, text)


def _comment_document(comment) -> ColumnElement:
    return func.to_tsvector(_TS_CONFIG, comment.body)


def _escape_like(value: str) -> str:
    """Makes % and _ literal characters instead of wildcards."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _search_condition(search: str) -> ColumnElement:
    """
    A top-level task matches when any of these matches the search text:
    its title (substring, as before), its title or description (full-text),
    one of its comments, one of its subtasks, or a comment on one of its subtasks.
    The board lists top-level tasks only, so subtask and comment hits surface their parent.
    """
    query = func.websearch_to_tsquery(_TS_CONFIG, search)
    subtask = aliased(Task)
    comment_on_task = exists().where(
        Comment.task_id == Task.id, _comment_document(Comment).op("@@")(query)
    )
    subtask_matches = exists().where(
        subtask.parent_task_id == Task.id,
        or_(
            _task_document(subtask).op("@@")(query),
            subtask.title.ilike(f"%{_escape_like(search)}%", escape="\\"),
        ),
    )
    comment_on_subtask = (
        exists()
        .where(subtask.parent_task_id == Task.id, Comment.task_id == subtask.id)
        .where(_comment_document(Comment).op("@@")(query))
    )
    return or_(
        Task.title.ilike(f"%{_escape_like(search)}%", escape="\\"),
        _task_document(Task).op("@@")(query),
        comment_on_task,
        subtask_matches,
        comment_on_subtask,
    )


async def get_by_id(db: AsyncSession, task_id: uuid.UUID) -> Task | None:
    return await db.get(Task, task_id)


async def create(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    title: str,
    description: str | None,
    status: TaskStatus,
    priority: TaskPriority,
    assignee_id: uuid.UUID | None,
    due_date: date | None,
    parent_task_id: uuid.UUID | None,
    created_by_id: uuid.UUID,
) -> Task:
    # New tasks go to the end of their status column — position is the max existing
    # position in that (project, status) bucket, plus one.
    max_position = await db.scalar(
        select(func.max(Task.position)).where(
            Task.project_id == project_id, Task.status == status
        )
    )
    task = Task(
        project_id=project_id,
        title=title,
        description=description,
        status=status,
        priority=priority,
        assignee_id=assignee_id,
        due_date=due_date,
        parent_task_id=parent_task_id,
        created_by_id=created_by_id,
        position=(max_position or 0) + 1,
    )
    db.add(task)
    await db.flush()
    return task


async def list_by_project(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    assignee_id: uuid.UUID | None = None,
    label_id: uuid.UUID | None = None,
    search: str | None = None,
    sort_by: TaskSortField = TaskSortField.POSITION,
    sort_order: SortOrder = SortOrder.ASC,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Task], int]:
    conditions = [Task.project_id == project_id, Task.parent_task_id.is_(None)]
    if status is not None:
        conditions.append(Task.status == status)
    if priority is not None:
        conditions.append(Task.priority == priority)
    if assignee_id is not None:
        conditions.append(Task.assignee_id == assignee_id)
    if search is not None and search.strip():
        conditions.append(_search_condition(search.strip()))

    base_query = select(Task).where(*conditions)
    count_query = select(func.count(func.distinct(Task.id))).where(*conditions)
    if label_id is not None:
        base_query = base_query.join(task_labels, task_labels.c.task_id == Task.id).where(
            task_labels.c.label_id == label_id
        )
        count_query = count_query.join(task_labels, task_labels.c.task_id == Task.id).where(
            task_labels.c.label_id == label_id
        )

    total = await db.scalar(count_query) or 0

    sort_column = _SORT_COLUMNS[sort_by]
    order_clause = sort_column.desc() if sort_order == SortOrder.DESC else sort_column.asc()

    result = await db.execute(
        base_query.order_by(order_clause).offset((page - 1) * page_size).limit(page_size)
    )
    return list(result.scalars().all()), total


async def list_subtasks(db: AsyncSession, *, parent_task_id: uuid.UUID) -> list[Task]:
    result = await db.execute(
        select(Task).where(Task.parent_task_id == parent_task_id).order_by(Task.position)
    )
    return list(result.scalars().all())


async def delete(db: AsyncSession, task: Task) -> None:
    await db.delete(task)
    await db.flush()


async def list_due_on(db: AsyncSession, *, due_date: date) -> list[Task]:
    """
    Assigned, not-done tasks due on exactly `due_date` — feeds the Celery Beat
    due-soon reminder job (called with tomorrow's date). An exact-date match, not
    "due within N days": the job runs once daily, so a task due tomorrow matches
    on exactly one run. Matching a range instead would re-notify the same
    still-overdue task every single day until it's completed.
    """
    result = await db.execute(
        select(Task).where(
            Task.due_date == due_date,
            Task.assignee_id.is_not(None),
            Task.status != TaskStatus.DONE,
        )
    )
    return list(result.scalars().all())
