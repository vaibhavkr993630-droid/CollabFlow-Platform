# Phase 7 — Frontend

> A real React app, finally consuming everything Phases 1-6 built. This is where CollabFlow
> stops being an API you exercise with curl and becomes a thing you can actually click around.

## Scope

| In | Out (later phases) |
|---|---|
| Vite + React 19 + TypeScript + Tailwind v4 | Backend containers and Compose stack (Phase 8) |
| Auth, dashboard, Kanban board, task detail, notifications | Backend CI, structured logging (Phase 8) |
| WebSocket client with reconnect/backoff | Production hosting (Phase 9) |
| Two backend list endpoints the frontend needed | — |

## Why this phase touches the backend at all

Every prior phase built create/read-one/update/delete for its resources, but nothing to
**enumerate** a user's organizations or workspaces — there was never a UI that needed to answer
"which orgs does this user belong to" until now. Two endpoints closed that gap:

```
GET /api/organizations                          → organization_crud.list_for_user
GET /api/organizations/{organization_id}/workspaces → workspace_crud.list_for_user_in_org
```

`list_for_user` is the more interesting of the two: organizations aren't membership-modeled
directly — a user belongs to one either by owning it, or by being a member of at least one of its
workspaces. The obvious SQLAlchemy approach is a `UNION` of two `select(Organization)` queries.
It's also broken:

```python
# What looks reasonable and silently returns garbage:
stmt = select(Organization).where(Organization.owner_id == user_id).union(
    select(Organization).join(Workspace).join(WorkspaceMembership).where(...)
)
result = await db.execute(stmt)
orgs = result.scalars().all()  # returns raw first-column values, NOT Organization objects
```

SQLAlchemy's `.union()` on ORM-entity `select()`s produces a Core-level compound select that
doesn't preserve entity mapping — `.scalars()` on the result returns whatever the first selected
column's raw value is (here, organization names as bare strings) rather than hydrated
`Organization` instances. This only surfaces once a query actually exercises **both** branches —
a user who owns zero orgs but is invited into at least one — which is exactly the kind of case an
owner-only manual test misses and a real test suite (or a real second user clicking around)
catches. The fix: two separate `SELECT`s, merged and deduplicated by id in plain Python.

```python
async def list_for_user(db: AsyncSession, *, user_id: uuid.UUID) -> list[Organization]:
    owned = await db.execute(select(Organization).where(Organization.owner_id == user_id))
    via_workspace = await db.execute(
        select(Organization)
        .join(Workspace, Workspace.organization_id == Organization.id)
        .join(WorkspaceMembership, WorkspaceMembership.workspace_id == Workspace.id)
        .where(WorkspaceMembership.user_id == user_id)
    )
    by_id = {org.id: org for org in owned.scalars().all()}
    for org in via_workspace.scalars().all():
        by_id.setdefault(org.id, org)
    return list(by_id.values())
```

## The axios client: one refresh, not a refresh race

```typescript
let refreshPromise: Promise<string> | null = null

async function refreshAccessToken(): Promise<string> { ... }

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status !== 401 || originalRequest._retried) return Promise.reject(error)
    originalRequest._retried = true
    refreshPromise ??= refreshAccessToken().finally(() => { refreshPromise = null })
    const newToken = await refreshPromise
    originalRequest.headers.Authorization = `Bearer ${newToken}`
    return apiClient(originalRequest)
  },
)
```

A dashboard page fires several requests at once on load. If the access token has expired, all of
them hit 401 near-simultaneously. Without coordination, each would independently call
`/api/auth/refresh` — a thundering herd against the auth endpoint, and a real risk of the backend
issuing (and the client racing to store) several different new access tokens. The shared
`refreshPromise` means the *first* 401 triggers the refresh call; every other concurrent 401
awaits that same in-flight promise instead of starting its own. `_retried` on the request config
prevents infinite retry loops if the refreshed token still comes back 401.

## `useWebSocket`: the one High-effort piece of this phase

The brief calls for High effort specifically on genuinely hard architectural/concurrency
reasoning — Phase 4's backend WebSocket work got that treatment, and this hook is the frontend
counterpart. Full reasoning is in the hook's own docstring (`frontend/src/ws/useWebSocket.ts`);
the two decisions worth calling out:

- **`getUrl()` is called fresh on every connection attempt, not once at mount.** The access token
  refreshes independently in the background (see the axios interceptor above). A reconnect after
  a `4401` needs to build its URL with whatever the *current* token is, not one captured when the
  component first rendered — otherwise a reconnect after a token refresh would retry with the
  same already-invalid token forever.
- **Backoff resets to zero on every successful open.** A connection that's been stable for hours
  and drops once should start backing off from 1 second again, not carry over a long delay
  computed from some outage that happened a while ago. `4401` closes get a higher base delay than
  a generic close — retrying instantly with a token that was *just* rejected is more likely to be
  hammering a dead session than catching a race with an about-to-refresh token.

## Three bugs, found by actually running the app in a browser

**1. The `union()` bug above** — caught by a test exercising the invited-member branch, not
visible from reading the query.

**2. `page_size=200` against a `le=100` cap.** The Kanban board wanted "every task in one view"
and asked for 200 at once. Phase 3's task-list endpoint caps `page_size` at 100 and rejects
anything above it with a 422 — the board's fetch failed, and the UI's error handling silently
rendered that as an empty board rather than a visible error. Two fixes, not one: the request now
asks for the actual ceiling (100), and a 422 now surfaces as a visible error state instead of
disappearing into "no tasks."

**3. Vite's `fs.watch` doesn't reliably fire on a Windows-mounted drive under WSL2.** This
project's working tree lives under `/mnt/d/...`. A just-applied fix kept appearing not to work —
not because the fix was wrong, but because the dev server's HMR never picked up the file change,
so the browser kept running the pre-fix bundle. `server.watch.usePolling: true` in
`vite.config.ts` trades faster native filesystem events for polling that actually detects changes
in this environment.

## Files added

```
frontend/
  package.json, package-lock.json, tsconfig*.json, vite.config.ts, index.html
  src/
    main.tsx, App.tsx, index.css, vite-env.d.ts
    types/index.ts                    # hand-mirrors backend schemas/*.py response shapes
    api/*.ts                          # one thin typed module per backend resource
    auth/{AuthContext,ProtectedRoute}.tsx
    ws/{useWebSocket,useProjectSocket,useNotificationSocket,events}.ts
    pages/{LoginPage,RegisterPage,DashboardPage,ProjectPage}.tsx
    components/{Layout,KanbanBoard,KanbanColumn,TaskCard,TaskDetailPanel,NotificationsPanel}.tsx
backend/app/api/routers/{organizations,workspaces}.py   # list endpoints
backend/app/crud/{organization,workspace}.py            # list_for_user, list_for_user_in_org
backend/tests/test_workspaces.py                        # +4 tests
```

## How to verify

```bash
docker compose up -d postgres redis minio maildev
cd backend
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload &
pytest                            # 65/65

cd ../frontend
npm install
npx tsc -b                        # type-check, clean
npx oxlint                        # lint, clean
npm run build                     # production build succeeds
npm run dev                       # http://localhost:5173, proxies /api and /ws to :8000
```

## What Phase 8 builds on this

Phase 8 hardens the **backend**: a container image and a full Docker Compose stack, a CI
pipeline for the backend test suite, structured logging, and a real health check. It deliberately
does not containerize the frontend or add frontend checks to CI — this phase leaves the frontend
running standalone via `npm run dev`, and Phase 9 ships it as a static build on Vercel instead.
