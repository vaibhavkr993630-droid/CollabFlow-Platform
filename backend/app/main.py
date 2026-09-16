import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
from app.core.redis import close_redis_client, get_redis_client
from app.core.storage import ensure_bucket_exists
from app.ws.connection_manager import connection_manager
from app.ws.events import project_id_from_channel, user_id_from_notification_channel
from app.ws.notification_manager import notification_manager
from app.ws.redis_listener import run_pattern_listener

settings = get_settings()
logger = logging.getLogger(__name__)


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
async def health() -> dict[str, str]:
    return {"status": "ok"}
