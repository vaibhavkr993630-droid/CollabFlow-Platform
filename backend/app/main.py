import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import (
    activity,
    auth,
    comments,
    labels,
    organizations,
    projects,
    tasks,
    workspaces,
    ws,
)
from app.core.config import get_settings
from app.core.redis import close_redis_client, get_redis_client
from app.ws.connection_manager import connection_manager
from app.ws.redis_listener import run_redis_listener

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    redis = get_redis_client()
    listener_task = asyncio.create_task(run_redis_listener(redis, connection_manager))

    yield

    listener_task.cancel()
    try:
        await listener_task
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
app.include_router(ws.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
