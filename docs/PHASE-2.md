# Phase 2 — Auth & Core Domain

> Accounts, organizations, workspaces, projects, tasks, labels, and comments — with JWT auth
> and role-based access control guarding every write. This is the phase where CollabFlow
> becomes an app you can actually register into and do something with.

## Scope

| In | Out (later phases) |
|---|---|
| JWT auth: register / login / refresh / me | Activity log, filtering/search (Phase 3) |
| RBAC dependencies (workspace, project, task-via-project) | Real-time / WebSockets (Phase 4) |
| Project, Task, Label, Comment models + migration | Notifications, `@mention` delivery (Phase 5) |
| CRUD + REST endpoints for all of the above | File attachments (Phase 6) |

## Auth

`app/core/security.py` owns two concerns: password hashing (`passlib`, bcrypt) and JWT
issuance/verification (`python-jose`). Tokens carry a `type` claim (`access` or `refresh`) so a
refresh token can't be used where an access token is expected — `decode_token(token,
expected_type)` checks it explicitly, not just signature/expiry.

```
POST /api/auth/register   → create user, hash password
POST /api/auth/login      → verify password, issue {access_token, refresh_token}
POST /api/auth/refresh    → verify refresh token, issue a new access token
GET  /api/auth/me         → current user, via get_current_user
```

`get_current_user` (`app/core/deps.py`) is an `OAuth2PasswordBearer`-driven dependency: decode
the bearer token, look up the user, 401 if the token's invalid or the user's inactive.

## RBAC: three dependency factories, one pattern

```python
def require_workspace_role(min_role: Role): ...   # workspace_id from the path
def require_project_role(min_role: Role): ...      # project_id from the path
def require_task_project_role(min_role: Role): ...  # task_id from the path — loads the task,
                                                      # checks role in *its* project
```

All three follow the same shape: load the caller's membership row, compare `ROLE_RANK[role]`
against `ROLE_RANK[min_role]`, 403 if it's not enough. `require_task_project_role` is the odd
one out because some routes (task detail, comment creation) are keyed on `task_id`, not
`project_id` — there's no project ID in the URL to check against directly. It loads the `Task`
row itself and **returns it**, so the route handler receives an already-fetched, permission-
checked task instead of doing a second query.

Putting this in dependencies rather than `if` statements in route bodies means the permission
logic is:
- Declared in the endpoint's signature, visible without reading the function body.
- Testable in isolation (the RBAC test suite calls these directly).
- Reused identically across every route that needs it.

## The shared `Role` enum

Phase 1 had `WorkspaceRole` living on `app/models/workspace.py`, because workspaces were the
only thing with roles. Phase 2 needed the identical three-tier scheme (`owner` / `admin` /
`member`) for **project** membership too. Rather than duplicate the enum or have
`models/project.py` reach into `models/workspace.py` for something conceptually unrelated to
workspaces, `Role` and `ROLE_RANK` moved to their own module: `app/models/roles.py`.

```python
class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"

ROLE_RANK = {Role.MEMBER: 0, Role.ADMIN: 1, Role.OWNER: 2}

def member_role_column() -> SAEnum:
    return SAEnum(Role, name="member_role", values_callable=lambda e: [m.value for m in e])
```

`member_role_column()` backs **both** `workspace_memberships.role` and
`project_memberships.role` with the same named Postgres enum type — one `member_role` type in
the database, not two enums that happen to have identical values. The migration renames the old
`workspace_role` Postgres type to `member_role` accordingly.

## The domain models

**Project / ProjectMembership** — same shape as Workspace/WorkspaceMembership: creating a
project auto-seeds its creator as an Owner-role `ProjectMembership`, mirroring how creating a
workspace seeds its creator as Owner there.

**Task** — the busiest model:

| Column | Notes |
|---|---|
| `status` | enum: `todo` / `in_progress` / `in_review` / `done` |
| `priority` | enum: `low` / `medium` / `high` / `urgent` |
| `assignee_id` | nullable FK to `users.id` |
| `parent_task_id` | self-referential FK — subtasks are tasks whose parent is another task |
| `position` | plain int, reserved for Kanban drag-and-drop ordering in Phase 7's frontend |

Indexed on `project_id`, `assignee_id`, `status`, and `parent_task_id` — every one of those is a
"list tasks where..." query the API needs to serve.

**Label** — project-scoped, unique by `(project_id, name)`, joined to tasks through a
`task_labels` association table (plain many-to-many, no extra columns on the join).

**Comment** — `task_id`, `author_id`, `body`. `@mention` parsing is explicitly **not** built
here — see Deviations below.

## A real bug: `MissingGreenlet` on `Task.labels`

SQLAlchemy relationships are lazy-loaded by default: accessing `task.labels` triggers a query
*at attribute-access time*, not at load time. That's fine inside a request handler, where the
async session is still open — but FastAPI's response serialization (building the JSON body from
the Pydantic response model) happens through a path that **does not await** SQLAlchemy's async
lazy-load machinery. The first time a task-with-labels response actually got serialized, this
raised `MissingGreenlet: greenlet_spawn has not been called`.

Fix: `Task.labels` is declared `lazy="selectin"` — SQLAlchemy issues a second `SELECT ... WHERE
task_id IN (...)` immediately as part of the original query's result processing, so `.labels` is
already a populated Python list by the time serialization touches it. This is also, independently,
the right choice for listing a project's tasks with their labels — `selectin` loading avoids
issuing one extra query per task (N+1) the way naive lazy-loading would under concurrent access.

## Deviation from the original brief

The brief groups "comments, mentions" together under Task fields for this phase. `@mention`
parsing was deferred to Phase 5 instead, once the notification system exists to actually deliver
a mention notification to someone — building mention *parsing* with nothing to send is dead
code. Comments themselves ship in full now. This was a deliberate, confirmed scope decision, not
silently dropped or silently expanded.

## Files added or changed

```
backend/app/
  core/security.py                 # NEW — hashing + JWT
  core/deps.py                     # get_current_user, require_{workspace,project,task_project}_role
  core/slugs.py                    # NEW — org/workspace slug generation
  api/routers/{auth,organizations,workspaces,projects,tasks,labels,comments}.py
  crud/{user,organization,workspace,project,task,label,comment}.py
  schemas/{auth,user,organization,workspace,project,task,label,comment}.py
  services/{auth,organization,workspace,project,task,label,comment}_service.py
  models/roles.py                  # NEW — shared Role, ROLE_RANK, member_role_column()
  models/{project,task,label,comment}.py
  models/workspace.py              # Role/ROLE_RANK moved out
backend/migrations/versions/3690234f411b_phase2_core_domain.py
backend/tests/{conftest,helpers,test_auth,test_workspaces,test_projects,test_tasks}.py
```

## How to verify

```bash
docker compose up -d postgres redis
cd backend
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head        # now at 3690234f411b
uvicorn app.main:app --reload &
pytest
```

`alembic downgrade base` still cleanly tears everything down, both migrations included.

## What Phase 3 builds on this

- Every mutation this phase introduced (task create/update/delete, comment create, membership
  changes) becomes something `ActivityLog` records.
- Task list filtering/sorting/search operates on exactly the `Task` columns this phase indexed.
