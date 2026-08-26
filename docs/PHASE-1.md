# Phase 1 — Foundation

> The identity and tenancy layer, a typed settings system, an async database stack, and a
> migration chain. Nothing user-facing yet — this phase exists so every later phase starts
> from a running app with a real schema.

## Scope

| In | Out (later phases) |
|---|---|
| FastAPI app + `/health` | Auth endpoints (Phase 2) |
| Typed settings (`pydantic-settings`) | RBAC enforcement (Phase 2) |
| Async SQLAlchemy engine + session dependency | Projects / tasks / comments (Phase 2) |
| `User`, `Organization`, `Workspace`, `WorkspaceMembership` models | Real-time / WebSockets (Phase 4) |
| Alembic (async) + first migration | Background jobs (Phase 5) |
| `docker-compose.yml` for Postgres / Redis / MinIO | Frontend (Phase 7) |

## The data model

CollabFlow is multi-tenant. The ownership hierarchy is:

```
Organization  ─ owner_id → User
     │
     └──< Workspace  (slug unique per organization)
              │
              └──< WorkspaceMembership ─ user_id → User
                        role: owner | admin | member
```

### `users`

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` | PK, `uuid4` app-side |
| `email` | `varchar(255)` | unique, indexed |
| `hashed_password` | `varchar(255)` | populated in Phase 2 |
| `full_name` | `varchar(255)` | |
| `is_active` | `bool` | default `true` |
| `created_at` / `updated_at` | `timestamptz` | server defaults, `onupdate` on the latter |

### `organizations`

The billing / ownership boundary. `slug` is globally unique and indexed; `owner_id` is a
FK to `users.id`. `workspaces` relationship cascades delete-orphan.

### `workspaces`

A team space inside an organization. `slug` is unique **per organization** — the constraint is
`UniqueConstraint("organization_id", "slug", name="uq_workspace_org_slug")`, not a unique
column. `organization_id` is indexed for the common "list workspaces in this org" query.

### `workspace_memberships`

Join table between users and workspaces, carrying a `role`:

```python
class WorkspaceRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"

ROLE_RANK = {WorkspaceRole.MEMBER: 0, WorkspaceRole.ADMIN: 1, WorkspaceRole.OWNER: 2}
```

`ROLE_RANK` turns "does this user have at least `admin`?" into an integer comparison — Phase 2's
`require_workspace_role(min_role)` dependency uses it directly. One membership per
`(workspace_id, user_id)` via `uq_membership_workspace_user`; both FK columns are indexed.

## Key decisions

**UUID primary keys, generated in Python.** `mapped_column(PGUUID(as_uuid=True),
primary_key=True, default=uuid.uuid4)`. The ID exists before the row is flushed, which
simplifies building object graphs, and there's no integer-sequence enumeration surface on any
public identifier.

**Shared mixins for identity and timestamps.** `UUIDPrimaryKeyMixin` and `TimestampMixin` in
[`app/db/base.py`](../backend/app/db/base.py) — every model composes them, so PK and audit
columns are defined once.

**Postgres enum stored by value.** `values_callable=lambda enum_cls: [m.value for m in
enum_cls]` makes the database enum labels `'owner' / 'admin' / 'member'` (the `StrEnum`
values), not `'OWNER' / 'ADMIN' / 'MEMBER'` (the member names). The migration creates the type
explicitly with `create_type=False` on the column so Alembic doesn't try to create it twice.

**Async all the way down.** The engine is `create_async_engine(...)` over `asyncpg`; Alembic's
`env.py` runs migrations through `async_engine_from_config` + `connection.run_sync`. There is no
sync database path anywhere.

**Migrations are hand-written and reviewed.** `env.py` imports every model
(`from app.models import *`) so `Base.metadata` is complete, but the online migration path never
autogenerates — each script is authored and checked in deliberately.

**Config surface is complete from day one.** `Settings` already declares `jwt_secret_key`,
`redis_url`, etc., even though Phase 1 doesn't read them. Adding a phase shouldn't mean
hunting for "where do settings go" — they go here.

## Files added

```
backend/
  pyproject.toml                     # deps, ruff, pytest config
  alembic.ini
  .env.example
  app/
    main.py                          # FastAPI app + CORS + /health
    core/config.py                   # Settings
    db/base.py                       # Base, UUIDPrimaryKeyMixin, TimestampMixin
    db/session.py                    # async engine, session, get_db()
    models/__init__.py               # re-exports for Base.metadata
    models/user.py
    models/organization.py
    models/workspace.py              # Workspace, WorkspaceMembership, WorkspaceRole, ROLE_RANK
  migrations/
    env.py                           # async migration runner
    script.py.mako
    versions/34d09d87098c_phase1_foundation.py
docker-compose.yml
```

## How to verify

```bash
docker compose up -d postgres redis
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
```

Expected: four tables (`users`, `organizations`, `workspaces`, `workspace_memberships`), one
enum type (`workspace_role`), and Alembic's `alembic_version` at revision `34d09d87098c`.

```bash
uvicorn app.main:app --reload
curl -s localhost:8000/health      # {"status":"ok"}
open http://localhost:8000/docs    # OpenAPI UI (just /health for now)
```

`alembic downgrade base` cleanly drops everything, enum included.

## What Phase 2 builds on this

- `User.hashed_password` gets populated by a `passlib` context.
- `WorkspaceRole` / `ROLE_RANK` become the basis of `require_workspace_role`.
- `get_db` is the session dependency every service function receives.
- The migration chain continues from `34d09d87098c` as `down_revision`.
