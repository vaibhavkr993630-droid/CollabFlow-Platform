# Phase 5 — Notifications & Background Jobs

> Every event a user actually cares about — being mentioned, assigned, invited, or having a
> task due tomorrow — now reaches them two ways: live in-app and via email, without the
> triggering request waiting on either.

## Scope

| In | Out (later phases) |
|---|---|
| `Notification` model + migration | File attachments (Phase 6) |
| Per-user notification WebSocket, generalized from project rooms | Frontend notification UI (Phase 7) |
| Celery + email + daily due-soon reminder | — |
| `@mention` parsing (closes a Phase 2 deferral) | — |

## One choke point: `create_and_dispatch`

```python
async def create_and_dispatch(db, redis, *, user_id, type, title, body,
                               project_id=None, task_id=None) -> Notification:
    notification = await notification_crud.create(db, ...)
    await db.commit()                              # its own unit of work
    await db.refresh(notification)

    await publish_notification_event(redis, user_id=user_id, notification={...})  # live

    recipient = await user_crud.get_by_id(db, user_id)
    if recipient is not None:
        from app.workers.tasks import send_notification_email   # deferred import
        send_notification_email.delay(recipient.email, title, body)  # always, regardless of connection

    return notification
```

Every trigger in the codebase — task assignment, workspace/project invite, `@mention` — calls
through this one function rather than duplicating "persist, broadcast, queue email" at each call
site. Two things about it are deliberate, not incidental:

**It commits on its own, not inside the caller's transaction.** A single comment can `@mention`
several project members, so one `create_comment` call may invoke `create_and_dispatch` multiple
times in a loop. Each notification needs to succeed or fail independently — if the fourth
recipient lookup has a problem, the first three notifications (and the comment itself) shouldn't
roll back because of it. This is the same reasoning as Phase 4's broadcast-after-commit pattern,
applied one layer further: a side effect that shouldn't be held hostage to an unrelated later
step.

**The Celery import is inside the function, not at module level.** `app.workers.tasks` pulls in
Celery's app registration machinery, which the API process doesn't otherwise need to load at
import time. A deferred import keeps that coupling one-directional — the API can import
`notification_service` freely without dragging in the worker's setup, and the worker process
importing `notification_service` (which it does, indirectly, to build notification content)
doesn't create an import cycle.

## Real-time delivery: generalized, not duplicated

Phase 4 had one listener function tied specifically to project rooms. Rather than write a near-
identical second listener for notifications, `run_redis_listener` became generic:

```python
async def run_pattern_listener(
    redis: Redis, *, pattern: str,
    extract_id: Callable[[str], uuid.UUID | None],
    deliver: Callable[[uuid.UUID, dict], Awaitable[None]],
) -> None: ...
```

`main.py`'s lifespan now starts **two** long-lived tasks from this one implementation:

```python
project_listener = asyncio.create_task(run_pattern_listener(
    redis, pattern="project:*:events",
    extract_id=project_id_from_channel, deliver=connection_manager.send_to_project))

notification_listener = asyncio.create_task(run_pattern_listener(
    redis, pattern="user:*:notifications",
    extract_id=user_id_from_notification_channel, deliver=notification_manager.send_to_user))
```

`NotificationConnectionManager` (`app/ws/notification_manager.py`) is `ConnectionManager`'s
sibling — same snapshot-before-iterating pattern to avoid Phase 4's bug #4 (live mutation during
broadcast) — but keyed only by `user_id`, since notifications aren't scoped to any project room.

`WS /ws/notifications` uses `get_current_user_ws`, not `require_ws_project_role` — it only needs
"is this a valid, active user," no membership check, because a user should be notified about a
project even when they don't currently have that project's room open.

## Triggers, wired into existing services

No new endpoints exist purely to fire a notification — each trigger lives inside the service
call that already causes the underlying event:

| Trigger | Where | Note |
|---|---|---|
| `@mention` in a comment | `comment_service.create_comment` | Resolved by email (`app/core/mentions.py`) — no username field exists on `User`. Silent no-op if the mentioned email isn't an actual project member. |
| Task assigned | `task_service` (create + reassignment) | Skipped when a user assigns a task to themselves. |
| Workspace invite | `workspace_service.invite_member` | |
| Project invite | `project_service.invite_member` | |
| Task due tomorrow | `workers/tasks.py::send_due_soon_reminders` (Celery Beat, daily) | See below for why "tomorrow" and not a range. |

Every router touching one of these now takes an injected `Redis` client alongside the existing
`AsyncSession`, threading it through to the service call — the same pattern Phase 4 established
for task/comment broadcasts, now extended to notification dispatch.

## Why "due exactly tomorrow," not "due within N days"

```python
# app/workers/tasks.py (abbreviated)
tomorrow = date.today() + timedelta(days=1)
tasks_due = await task_crud.list_due_on(db, due_date=tomorrow)
```

The reminder job runs once daily. An exact-date match fires **once** per task — the single day
before it's due. A range match ("due within 2 days") sounds more thorough but would re-notify the
same still-open, still-overdue task every day the job runs until someone marks it done: a spam
generator dressed up as diligence. The honest tradeoff of the exact-match choice: a task whose
due date passes during job downtime (the Beat scheduler wasn't running that day) never gets
reminded. Accepted for this project's scope, not silently ignored.

## A real bug: MailDev's `:latest` tag

Adding MailDev to `docker-compose.yml` with `image: maildev/maildev:latest` produced a container
that was genuinely running and healthy — process up, SMTP port listening, confirmed via container
logs — but whose web UI and `/email` REST endpoint both returned 404. `:latest` had drifted to a
`3.0.0-rc.3` release candidate with a different, API-only routing scheme than the stable version
the setup assumed. The fix was pinning to `2.1.0`, a known-stable release, which resolved it
immediately.

The lesson generalizes: `:latest` on a fast-moving dev-tool image is a real operational risk, not
a hygiene nitpick — and the fix here mattered because the container's actual listening state was
checked (logs, the process was genuinely fine) before concluding the problem was configuration on
the app side rather than the image itself.

## A test-writing lesson, not a code bug

Early versions of the notification tests asserted the wrong count after an invite-then-assign
flow — expecting one notification, observing two. The app was correct throughout: inviting a
user to a project *also* creates a `project_invite` notification for that same recipient, and a
test that both invites and assigns a task to the same user in one flow legitimately triggers both
`project_invite` and `task_assigned`. The fix was correcting the test's expectation after
confirming the app's actual behavior was right — not adjusting an assertion until it happened to
pass.

## Files added or changed

```
backend/app/
  models/notification.py             # NEW — Notification, NotificationType
  crud/notification.py               # NEW
  schemas/notification.py            # NEW
  services/notification_service.py   # NEW — create_and_dispatch
  api/routers/notifications.py       # NEW — REST list/unread-count/mark-read
  api/routers/ws.py                  # WS /ws/notifications
  ws/notification_manager.py         # NEW
  ws/redis_listener.py               # run_redis_listener -> generic run_pattern_listener
  ws/events.py                       # publish_notification_event, user_id_from_notification_channel
  core/deps.py                       # get_current_user_ws
  core/mentions.py                   # NEW — @mention extraction by email
  core/email.py                      # NEW — blocking smtplib send
  core/config.py                     # smtp_host/port/from
  workers/celery_app.py              # NEW
  workers/tasks.py                   # NEW — send_notification_email, send_due_soon_reminders
  services/{comment,task,workspace,project}_service.py  # trigger wiring
  api/routers/{projects,workspaces}.py                  # Redis dependency threaded through
backend/migrations/versions/c18c809922b5_phase5_notifications.py
backend/tests/test_notifications.py
backend/tests/test_websocket.py        # + notification WS coverage
docker-compose.yml                     # maildev, pinned 2.1.0
```

## How to verify

```bash
docker compose up -d postgres redis
cd backend
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head        # now at c18c809922b5
uvicorn app.main:app --reload &
pytest
```

To exercise email delivery end to end, also bring up MailDev and a worker:

```bash
docker compose up -d maildev
celery -A app.workers.celery_app worker --loglevel=info &
celery -A app.workers.celery_app beat --loglevel=info &
# trigger a notification via the API, then check http://localhost:1080
```

## What Phase 6 builds on this

- The `Redis`-injected-alongside-`AsyncSession` pattern this phase extended from Phase 4 is the
  same shape Phase 6's attachment endpoints use.
- `create_and_dispatch`'s "always queue, regardless of connection state" pattern is the template
  for any future notification type — attachments could plausibly add one later without touching
  the dispatch mechanism itself.
