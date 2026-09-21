import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers import (
    activity,
    attachments,
    auth,
    comments,
    labels,
    notifications,
    organizations,
    projects,
    tasks,
    workspaces,
    ws,
)
from app.core.config import get_settings
from app.core.logging_config import setup_logging
from app.core.redis import close_redis_client, get_redis_client
from app.core.storage import ensure_bucket_exists
from app.db.session import get_db
from app.ws.connection_manager import connection_manager
from app.ws.events import project_id_from_channel, user_id_from_notification_channel
from app.ws.notification_manager import notification_manager
from app.ws.redis_listener import run_pattern_listener

setup_logging()
settings = get_settings()
logger = logging.getLogger(__name__)

if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        integrations=[FastApiIntegration()],
        traces_sample_rate=0.1,
    )


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    ensure_bucket_exists()
    redis = get_redis_client()
    project_listener = asyncio.create_task(
        run_pattern_listener(
            redis,
            pattern="project:*:events",
            extract_id=project_id_from_channel,
            deliver=connection_manager.send_to_project,
        )
    )
    notification_listener = asyncio.create_task(
        run_pattern_listener(
            redis,
            pattern="user:*:notifications",
            extract_id=user_id_from_notification_channel,
            deliver=notification_manager.send_to_user,
        )
    )

    yield

    for task in (project_listener, notification_listener):
        task.cancel()
    for task in (project_listener, notification_listener):
        try:
            await task
        except asyncio.CancelledError:
            pass
    await close_redis_client()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(organizations.router)
app.include_router(workspaces.router)
app.include_router(workspaces.member_router)
app.include_router(projects.router)
app.include_router(projects.member_router)
app.include_router(tasks.project_router)
app.include_router(tasks.task_router)
app.include_router(labels.router)
app.include_router(comments.router)
app.include_router(activity.project_router)
app.include_router(activity.task_router)
app.include_router(notifications.router)
app.include_router(attachments.router)
app.include_router(ws.router)
app.include_router(ws.notifications_router)


@app.get("/health")
async def health(
    db: AsyncSession = Depends(get_db), redis: Redis = Depends(get_redis_client)
) -> dict[str, str]:
    """
    Checks the two dependencies every request actually needs (DB, Redis) rather
    than just confirming the process is alive — a load balancer or orchestrator
    relying on this to decide whether to route traffic here wants to know "can
    this instance actually serve requests," not just "is it running." MinIO/SMTP
    aren't checked: neither is on the critical path for most endpoints, so an
    outage there shouldn't take this instance out of rotation entirely.
    """
    failures = []

    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Health check: database unreachable")
        failures.append("database")

    try:
        await redis.ping()
    except Exception:
        logger.exception("Health check: redis unreachable")
        failures.append("redis")

    if failures:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "unhealthy", "failed": failures},
        )
    return {"status": "ok"}
