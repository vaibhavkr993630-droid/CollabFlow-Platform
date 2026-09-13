# Phase 3 — Activity Log & Search

> Every state-changing action now leaves an audit trail, and task lists gain real server-side
> filtering, sorting, search, and pagination — the two features every project-management tool
> needs before it's usable with more than a handful of tasks.

## Scope

| In | Out (later phases) |
|---|---|
| `ActivityLog` model + migration | Real-time delivery of activity (Phase 4) |
| Activity logged from every write in Phase 2's services | Notifications from activity (Phase 5) |
| Task filter/sort/search/pagination query params | — |
| Activity feed endpoints (project-wide, per-task) | — |

## The `ActivityLog` model

```python
class ActivityLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "activity_logs"

    project_id: Mapped[uuid.UUID]          # required — every entry belongs to a project
    task_id: Mapped[uuid.UUID | None]      # ON DELETE SET NULL
    actor_id: Mapped[uuid.UUID]            # who did it
    action: Mapped[ActivityAction]         # enum — see below
    summary: Mapped[str]                   # human-readable, generated at log time
    activity_metadata: Mapped[dict | None] # JSONB — structured detail
```

**Append-only.** Nothing in the codebase updates or deletes an `ActivityLog` row — it's written
once by `activity_service.log(...)` and read by the two feed endpoints. That's a design
invariant, not (yet) a database-enforced one.

**Why `activity_metadata` and not `metadata`** — `Base` is a SQLAlchemy `DeclarativeBase`
subclass, and `metadata` is already a reserved attribute on every declarative model (it points at
the `MetaData` collection of table definitions). A column literally named `metadata` would shadow
that.

**Why `task_id` is `ON DELETE SET NULL`, verified, not assumed:**

```sql
task_id UUID REFERENCES tasks(id) ON DELETE SET NULL
```

A `CASCADE` here would destroy a task's audit trail the moment the task itself is deleted —
backwards for a feature whose entire point is "what happened." A plain restrictive FK would block
task deletion entirely once it had any history, which is worse. `SET NULL` keeps every historical
entry (the log line `"Task 'Ship v1' was created"` still exists and still reads correctly) while
letting the specific task reference go. This was checked against a live migrated Postgres
instance — delete a task with history, then query `activity_logs` — confirming every entry that
referenced it (not just a synthetic "task deleted" row) had `task_id` set to `NULL`.

## Logging: inside the transaction, not after it

```python
# app/services/task_service.py (abbreviated)
async def update_task(db, *, task, patch, actor_id):
    ...
    await activity_service.log(
        db, project_id=task.project_id, task_id=task.id, actor_id=actor_id,
        action=ActivityAction.TASK_UPDATED, summary=f"Updated task '{task.title}'",
    )
    # caller commits — the log row and the task update land in the same transaction
```

`activity_service.log` flushes, it doesn't commit. The router/service layer that owns the
request commits once, at the end. This means: if anything later in that same request fails and
the transaction rolls back, the activity entry rolls back with it — there is no way to end up
with a log entry describing something that didn't actually happen.

Every Phase 2 write path now calls this: project creation, member invite, task create / update /
delete, comment add, label create.

## Task list: filter, sort, search, paginate

```
GET /api/projects/{project_id}/tasks
    ?status=in_progress
    &priority=high
    &assignee_id=<uuid>
    &label_id=<uuid>
    &search=migration
    &sort_by=due_date&sort_order=asc
    &page=1&page_size=20
```

All parameters are optional — an unfiltered call behaves exactly as it did in Phase 2, aside from
the response envelope (see below). `crud/task.py::list_by_project` builds the query
conditionally: each filter only adds a `WHERE` clause if it was actually passed, `label_id`
`JOIN`s `task_labels` only when present, and total count is computed via a matching
`COUNT(DISTINCT ...)` query rather than `len()` on the paginated result set.

**`sort_by` is a closed enum** (`TaskSortField`: `created_at`, `due_date`, `priority`, `status`,
`position`, `title`), mapped server-side to real SQLAlchemy columns — never a raw client string
interpolated into `ORDER BY`. Sorting by `status` or `priority` produces `todo < in_progress <
in_review < done` and `low < medium < high < urgent` respectively, because Postgres orders native
enum values by their *definition* order, and both enums were defined in that order back in Phase
2 specifically so this would fall out for free later.

**Response envelope changed**, deliberately, as a breaking change to Phase 2's contract:

```python
class TaskListResponse(BaseModel):
    items: list[TaskRead]
    total: int
    page: int
    page_size: int
```

A bare list can't carry a total count, and bolting pagination onto a second endpoint alongside
the original would mean maintaining two task-list code paths indefinitely. One endpoint, one
contract, changed once, while the whole app is still pre-1.0.

## A gap closed along the way

Phase 2 built `Label` and the `task_labels` association table, but no endpoint ever *attached* a
label to a task — there was no way to test the new `label_id` filter against real data. Rather
than ship an untestable filter, `TaskUpdate` gained:

```python
label_ids: list[uuid.UUID] | None = None  # full replace, not incremental add/remove
```

Full-replace (send the complete desired label set, not "add this / remove that") was chosen
because it's the simpler contract for a v1 editor that re-sends a whole multi-select's state on
every save — incremental add/remove endpoints can be added later if the UI ever needs them
independently.

## Activity feed endpoints

```
GET /api/projects/{project_id}/activity?page=1&page_size=20   → require_project_role(MEMBER)
GET /api/tasks/{task_id}/activity?page=1&page_size=20         → require_task_project_role(MEMBER)
```

Both reuse Phase 2's RBAC dependencies unchanged — no new permission concept was needed, because
"can you see this project's/task's activity" is exactly "are you a member of this project,"
which was already solved.

## Files added or changed

```
backend/app/
  models/activity.py                # NEW — ActivityLog, ActivityAction
  models/task.py                    # TaskSortField, SortOrder enums
  crud/activity.py                  # NEW — list_by_project, list_by_task
  crud/task.py                      # list_by_project: filter/sort/search/paginate
  services/activity_service.py      # NEW — log(...)
  services/{comment,label,project,task}_service.py  # call activity_service.log after writes
  schemas/activity.py                # NEW — ActivityLogRead, ActivityLogListResponse
  schemas/task.py                    # TaskUpdate.label_ids, TaskListResponse envelope
  api/routers/activity.py            # NEW — project_router, task_router
  api/routers/{labels,projects,tasks}.py  # query params, activity feed wiring
backend/migrations/versions/fd31448fb5dc_phase3_activity_log.py
backend/tests/test_activity_and_search.py
```

## How to verify

```bash
docker compose up -d postgres redis
cd backend
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head        # now at fd31448fb5dc
uvicorn app.main:app --reload &
pytest
```

`alembic downgrade base` still tears everything down cleanly across all three migrations.

## What Phase 4 builds on this

- Every `activity_service.log(...)` call becomes a natural place to also publish a WebSocket
  event — the same "what happened" data, delivered live instead of polled.
- The RBAC dependencies this phase reused unchanged are exactly what Phase 4's WebSocket
  connection handshake authenticates against.
