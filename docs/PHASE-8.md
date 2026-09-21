# Phase 8 — Hardening

> The app already worked. This phase makes it something you can run the same way on any machine,
> check automatically on every push, and diagnose when something goes wrong: a container image, a
> one-command full stack, a CI pipeline, machine-readable logs, error tracking, and a health check
> that tells the truth.

## Scope

| In | Out (deliberately) |
|---|---|
| `backend/Dockerfile` and a full `docker-compose.yml` (API, worker, beat, one-shot migrate) | Containerizing the frontend (it runs via `npm run dev`; Phase 9 ships it as a static build) |
| GitHub Actions CI for the backend: lint, migrations, full test suite | Frontend checks in CI (`tsc` / `oxlint` / `build` are run by hand for now) |
| Structured JSON logging for the API **and** the Celery worker | Log shipping, request-ID correlation |
| Optional Sentry, inert unless configured | Creating an actual Sentry project |
| `/health` that checks Postgres and Redis | Checking MinIO / SMTP (see below) |
| Presigned-URL fix for containerized deployments | Publishing the image to a registry |

The two commits of this phase split along that line: **the application code** (logging, Sentry,
health, presigned URLs) first, then **the packaging around it** (Docker, Compose, CI).

## The full stack in containers

```
postgres ─┐
redis ────┼─(healthy)──► migrate (runs `alembic upgrade head`, exits 0) ──┬──► backend  :8000
minio ────┘                                                                ├──► worker   (Celery)
maildev                                                                    └──► beat     (Celery Beat)
```

Three details are worth being able to explain:

**`migrate` is a one-shot service, and the other three wait on it.** Each of `backend`, `worker`
and `beat` declares `depends_on: migrate: condition: service_completed_successfully`. Without
that, three containers would each be racing to build the schema against their own first request or
task. With it, the schema is applied exactly once, and nothing that needs it starts until it has
exited with code 0.

**Health checks drive start order.** Postgres, Redis and MinIO each have a `healthcheck`, and the
services that need them use `condition: service_healthy`. "The container started" is not the same
as "the database accepts connections", and a health-gated start order is what turns the first into
the second.

**One image, four roles.** `migrate`, `backend`, `worker` and `beat` all build from the same
`backend/Dockerfile`; only the `command` differs. The image is a plain runtime image (no build
toolchain, `tests/` excluded through `.dockerignore`), installed with a regular
`pip install .` rather than an editable one: a runtime image never re-resolves the package after
code changes, those arrive by rebuilding.

## CI: what runs, and why MinIO is started by hand

`.github/workflows/backend-ci.yml` runs on every push or pull request that touches `backend/**`:

1. Start Postgres and Redis as GitHub Actions **service containers**.
2. Start MinIO with a plain `docker run` step (explained below).
3. `ruff check app tests migrations`.
4. Create the test database, then `alembic upgrade head` against a real Postgres.
5. `pytest -v` — the full suite, against real Postgres, Redis and MinIO.

**Why MinIO isn't a service container.** Service containers can't override the image's command.
The official `minio/minio` image needs `server /data` as an argument to start at all — with its
bare default command it just prints usage and exits. GitHub's `services:` block has no field for
that argument, so MinIO is started directly with `docker run ... minio/minio server /data` instead.

**Why `alembic upgrade head` is its own step.** The test suite builds its schema with
`Base.metadata.create_all`, which is generated fresh from the current models on every run. That
means it can never notice a hand-written migration drifting away from the models it is supposed to
reproduce. Several bugs in this project (enum name vs. value mismatches, a migration trying to
create the same Postgres enum twice) only ever showed up when a migration ran for real, so the
pipeline runs one.

## Structured logging

`app/core/logging_config.py` has a small stdlib-only `JSONFormatter`: one JSON object per line
with `timestamp`, `level`, `logger`, `message`, and an `exception` field when there is a traceback.
JSON lines can be filtered, grouped and searched by a log platform; plain text has to be parsed
with regexes first.

Three things had to be right for it to actually work:

- **The Celery worker needs its own hook.** On startup Celery takes over the root logger, so a
  `setup_logging()` call made at import time is silently overwritten. Celery's documented hook is
  the `after_setup_logger` / `after_setup_task_logger` signals, which is what `celery_app.py` uses.
- **Root stays at INFO, always.** With `settings.debug=True` an early version set the root logger
  to DEBUG — which applies to *every* library, not just this app, and buried real startup output
  under hundreds of botocore internals. Debug verbosity is now opted into per logger
  (`logging.getLogger("app").setLevel(DEBUG)`), and every module logger already lives under `app.*`.
- **`echo=False` on the SQLAlchemy engine.** `echo=True` attaches SQLAlchemy's own handler *in
  addition to* propagating to root, so once the JSON handler existed every SQL line printed twice —
  once plain, once as JSON.

## Sentry, wired but optional

`sentry-sdk[fastapi]` is initialized in `main.py` only `if settings.sentry_dsn:`. With no DSN
configured it never initializes, and the app behaves identically. The honest description is
"integrated behind a config flag, no Sentry project created yet".

## `/health` that tells the truth

The original `/health` returned `{"status": "ok"}` whenever the process was running — which says
nothing about whether it can serve a request. Now:

```python
await db.execute(text("SELECT 1"))     # Postgres reachable?
await redis.ping()                      # Redis reachable?
# either failing -> 503 {"detail": {"status": "unhealthy", "failed": ["redis"]}}
```

A load balancer or orchestrator reading this decides whether to send traffic here, and it wants
"can this instance serve requests", not "is the process alive". **MinIO and SMTP are deliberately
not checked**: they are not on the critical path for most endpoints, so an outage there should not
take the whole instance out of rotation.

## The presigned-URL bug (the good interview story)

Inside Compose, the backend talks to MinIO at `http://minio:9000`. That is right for its own
uploads and deletes. But the same client also generated download URLs — and a presigned URL bakes
in the host of the client that signed it (AWS Signature V4 signs the host as part of the request).
So a browser, or `curl` on the host, got back `http://minio:9000/...`: a syntactically perfect URL
that only resolves inside the Docker network.

Why it was hard to see: nothing about the URL *looks* wrong, and no unit test checking its shape
would fail. It only breaks when something outside the network tries to use it.

The fix is a second boto3 client, `get_presign_client()` in `app/core/storage.py`, configured with
a separate `S3_PUBLIC_ENDPOINT_URL` and used **only** to compute the signature. All real I/O
(`put` / `get` / `delete` / `head`) still goes through the original internal client. In Compose the
public URL is `http://localhost:9000`; without Docker it is left unset and falls back to the
internal one, where both are already `localhost:9000`.

## What was verified for real

Not just "the tests pass" — the containerized stack was brought up and exercised:

| Check | Result |
|---|---|
| `docker compose up -d --build`: all 7 services | `migrate` exited 0; backend, worker, beat, postgres, redis, minio, maildev up |
| `/health` with everything up | `200 {"status":"ok"}` |
| `docker compose stop redis`, then `/health` | `503 {"failed":["redis"]}` |
| `docker compose start redis`, then `/health` | back to `200` |
| Backend log lines | every one is JSON |
| Upload a file, fetch it via the presigned URL **from the host**, `cmp` the bytes | URL host is `localhost:9000`, bytes identical |
| `ruff check app tests migrations` | clean |
| `pytest` against real Postgres, Redis, MinIO | 65 passed |

## Known simplifications

- **The container runs as root.** Celery prints a `SecurityWarning` about running the worker with
  superuser privileges on startup. The Dockerfile has no non-root `USER`; adding one is a small,
  worthwhile change before real production use.
- **Celery's startup banner is not JSON.** Real log records are; the ASCII-art banner and that
  one warning are printed by Celery itself before the formatter is attached.
- **CI does not publish the image anywhere.** It lints, migrates and tests. Pushing to a registry
  would be the next step if deploys ever came from CI.
- **CI covers only the backend.** The frontend's `tsc`, `oxlint` and production build are not yet
  part of any pipeline.
- **`JWT_SECRET_KEY` and the MinIO credentials in `docker-compose.yml` are development defaults.**
  Fine for a local stack; Phase 9 replaces them with real secrets set in the hosting platform.

## Files added or changed

```
backend/
  Dockerfile, .dockerignore                 # NEW — runtime image
  app/core/logging_config.py                # NEW — JSONFormatter, setup_logging
  app/core/config.py                        # s3_public_endpoint_url, sentry_dsn
  app/core/storage.py                       # get_presign_client, _build_client
  app/db/session.py                         # echo=False
  app/main.py                               # setup_logging(), Sentry init, real /health
  app/workers/celery_app.py                 # JSON logging via Celery signals
  .env.example, pyproject.toml              # new settings, sentry-sdk
docker-compose.yml                          # healthchecks, migrate/backend/worker/beat
.github/workflows/backend-ci.yml            # NEW — lint + migrations + tests
```

## How to verify

```bash
# The whole stack, in containers
docker compose up -d --build
curl -s localhost:8000/health                 # {"status":"ok"}
docker compose stop redis && curl -s -w " [%{http_code}]\n" localhost:8000/health
docker compose start redis

# Or: infra in Docker, backend on your machine
docker compose up -d postgres redis minio maildev
cd backend && pip install -e ".[dev]" && cp .env.example .env
alembic upgrade head && pytest && ruff check app tests migrations
```

## What Phase 9 builds on this

The same image runs in production. Phase 9 describes the hosted infrastructure as code, replaces
the development credentials above with real secrets, configures SMTP for real email delivery, and
deploys the frontend as a static build on Vercel — including the production WebSocket URL the
frontend needs when it and the backend are on different domains.
