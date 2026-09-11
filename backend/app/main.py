from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import auth, comments, labels, organizations, projects, tasks, workspaces
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name)

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


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
