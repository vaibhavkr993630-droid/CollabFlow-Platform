# Phase 4 — Real-Time

> Task and comment changes, and who's currently looking at a project, now propagate to every
> connected client live. No polling, no page refresh. This is the phase where CollabFlow starts
> to feel like the "Slack" half of the Jira × Slack pitch.

## Scope

| In | Out (later phases) |
|---|---|
| WebSocket endpoint, RBAC-authenticated | Notifications delivered off-request (Phase 5) |
| Redis pub/sub fan-out (multi-instance-ready) | File attachments (Phase 6) |
| Presence tracking (who's viewing a project) | Frontend WS client + reconnect logic (Phase 7) |
| Task/comment writes broadcast after commit | — |

## Why Redis pub/sub, when there's only one instance

```
REST write (any instance) ──▶ publish to Redis: project:{id}:events
                                       │
                    every instance's redis_listener task, subscribed
                    once to the pattern "project:*:events", receives it
                                       │
                     each instance's ConnectionManager fans it out only
                     to sockets that happen to be connected *to it*
```

A REST call that changes a task publishes to Redis rather than pushing to local WebSocket
clients directly — so a task updated via an API call served by instance A still reaches a
WebSocket client connected to instance B. This project's deployment runs one backend instance,
so that fan-out is presently a no-op round trip through Redis rather than something observably
necessary. The code path is identical either way, which is the point: horizontal scaling
readiness without a rewrite to add it later, at the cost of one extra Redis round-trip per event
today.

**`redis_listener.py` subscribes once**, to the pattern `project:*:events`, not once per active
project — a single long-lived background task (started in `main.py`'s `lifespan`, cancelled
cleanly on shutdown) handles every project's events. Opening a fresh subscription per project
would mean the number of Redis subscriptions scaling with active projects instead of staying
constant.

## `ConnectionManager`: local only, dumb on purpose

```python
class ConnectionManager:
    # (project_id, user_id) -> set[WebSocket] — a set because one user can hold
    # multiple tabs open to the same project.
    _connections: dict[uuid.UUID, dict[uuid.UUID, set[WebSocket]]]

    def connect(self, project_id, user_id, ws): ...
    def disconnect(self, project_id, user_id, ws): ...
    async def send_to_project(self, project_id, message): ...
```

It knows nothing about Redis, events, or what a message *means* — it only tracks which sockets
are live on this process and fans a dict out to them. `redis_listener.py` is the only caller of
`send_to_project`. Keeping the manager this dumb means it's trivially testable without Redis at
all (see `test_websocket.py`).

## Presence: a ref-counted Redis hash, not a set

```python
# app/ws/presence.py
async def join(redis, *, project_id, user_id) -> int:   # returns new connection count
async def leave(redis, *, project_id, user_id) -> int:  # returns remaining count
async def online_user_ids(redis, *, project_id) -> list[str]:
```

Backed by `HINCRBY project:{id}:presence {user_id} 1` on join and `HINCRBY ... -1` (+ a
conditional `HDEL` at zero) on leave — **a count, not a set membership flag**, because one user
can open multiple tabs to the same project. A plain set would report "offline" the moment *any*
one of a user's tabs closed, even with others still open. Redis-backed rather than an in-process
structure specifically so this stays correct if connections for the same user land on different
backend instances.

`GET /api/projects/{project_id}/presence` exposes `online_user_ids` over plain REST, for any
client that wants a snapshot without opening a socket first — and for tests, which don't need a
live WebSocket connection just to assert on presence state.

## The WebSocket route and its auth

```python
@router.websocket("/ws/projects/{project_id}")
async def project_websocket(
    websocket: WebSocket,
    project_id: uuid.UUID,
    user: User = Depends(require_ws_project_role(Role.MEMBER)),
    redis: Redis = Depends(get_redis_client),
) -> None:
```

`require_ws_project_role` is `require_project_role`'s WebSocket sibling: same role-rank check,
but it reads the JWT from a `?token=` query parameter (browsers' native WebSocket API can't set
an `Authorization` header on the handshake) and raises `WebSocketException` on failure instead of
`HTTPException` — FastAPI closes the socket with that code automatically, *before* `accept()` is
called, so a rejected connection never completes the handshake at all.

On connect, in this exact order:
1. `connection_manager.connect(...)` — register locally.
2. `presence.join(...)` — increment the Redis count, get back the new total.
3. **Send the presence snapshot to this socket, and fully await it.**
4. Only then, if this was the user's *first* connection (`connection_count == 1`), publish
   `PRESENCE_JOINED` to Redis.

Steps 3 and 4 are ordered deliberately — see bug #1 below for why swapping them breaks things.

## Broadcasting: after commit, not inside the transaction

```python
# app/services/task_service.py (abbreviated)
async def update_task(db, redis, *, task, patch, actor_id):
    ...
    await db.commit()
    await publish_event(redis, project_id=task.project_id,
                         event_type=WSEventType.TASK_UPDATED, data=..., actor_id=actor_id)
```

This is the opposite ordering from Phase 3's activity logging, deliberately: an activity log
entry rolling back with its transaction is correct (it describes something that, if the
transaction failed, didn't happen). A WebSocket broadcast is not transactional — once sent, a
client has already reacted to it. Publishing before commit risks announcing a change that then
fails to persist. So broadcasts happen strictly after `db.commit()` returns successfully.

## Four bugs, three of them concurrency-shaped

**1. Presence-snapshot / self-join ordering race.** Publishing `PRESENCE_JOINED` before sending
the direct snapshot let the (already-running) Redis listener task relay the client's own join
event back to it before the snapshot send even happened — the new client could see itself "join"
before it had any idea who else was online. Fixed by the ordering in the route above: snapshot
send fully completes before anything reaches Redis.

**2. WS auth wasn't overridable in tests.** An early version opened its own DB session by hand
inside the route (auth failure "needs" `websocket.close()`, not an exception — or so it seemed),
bypassing the same `Depends(get_db)` pattern every HTTP route uses. `tests/conftest.py`'s
database override had no effect on that path — tests would have silently exercised the real dev
database. Fixed by using `WebSocketException` from within a normal `Depends()`, which FastAPI
handles by closing the socket automatically before `accept()` — auth became a fully overridable
dependency like any other.

**3. Redis client singleton broke across pytest's per-test event loops.** The exact same failure
mode as the `NullPool` fix documented back in Phase 1/3 for the DB engine, here for
`redis.asyncio.Redis`: a module-level singleton binds to whichever event loop first constructs
it, and pytest-asyncio hands each test function a fresh loop — so any test after the first one to
touch Redis raised `RuntimeError: Event loop is closed`. Fixed with an autouse fixture
(`_reset_redis_client`) that closes and clears the singleton after every test.

**4. `send_to_project` mutated-during-iteration race.** `await websocket.send_json(...)` yields
control back to the event loop mid-broadcast; a real client disconnecting at that exact moment
runs its `finally` block's `connection_manager.disconnect()`, which mutates the very dict/set
`send_to_project` is mid-iteration over — raising a "changed size during iteration" error. This
surfaced during a full test run, not from the WebSocket tests in isolation, since it needs a
disconnect to land inside another send's await window. Fixed by snapshotting the connection dict
and every inner socket set into plain lists before the loop starts, decoupling the broadcast from
live mutable state.

## Known simplifications, stated rather than hidden

- **Token in the query string.** `?token=<jwt>` is the only way to authenticate a browser
  WebSocket handshake without a server round-trip first, but it means a short-lived access token
  can end up in server access logs. A production system would mint a short-lived, single-use WS
  ticket via an authenticated REST call instead of reusing the access token directly.
- **Pub/sub fan-out is unexercised at scale** — real code, run on every event, but this
  deployment has exactly one backend instance, so the cross-instance delivery it enables has
  never been observed to matter here. Documented rather than silently dropped.
- **`presence.leave` isn't atomic** — the decrement and the conditional delete-at-zero are two
  separate Redis calls. A rare concurrent-disconnect race at the exact moment a count hits zero
  could theoretically leave a stale zero-count hash entry. Not worth Lua scripting at this scope.
- **No client reconnect/backoff logic yet** — explicitly deferred to Phase 7's frontend WebSocket
  client.

## Files added or changed

```
backend/app/
  core/redis.py                    # NEW — singleton async Redis client
  ws/connection_manager.py         # NEW
  ws/events.py                     # NEW — WSEventType, publish_event, project_id_from_channel
  ws/presence.py                   # NEW — join/leave/online_user_ids
  ws/redis_listener.py             # NEW — pattern-subscribe + relay
  api/routers/ws.py                # NEW — WS /ws/projects/{project_id}
  api/routers/projects.py          # GET .../presence (REST)
  core/deps.py                     # require_ws_project_role
  main.py                          # lifespan: start/stop the Redis listener task
  services/{task,comment}_service.py  # publish_event after commit
backend/tests/test_websocket.py
```

## How to verify

```bash
docker compose up -d postgres redis
cd backend
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head       # unchanged this phase — no schema touches Redis
uvicorn app.main:app --reload &
pytest
```

No migration to check — Phase 4's state is entirely Redis-resident by design.

## What Phase 5 builds on this

- The same `ConnectionManager` / Redis pub/sub machinery gets a second channel namespace for
  per-user notification delivery, not just per-project events.
- `publish_event`'s after-commit pattern is exactly how Phase 5's Celery email task gets queued —
  after the notification row commits, not from inside its transaction.
