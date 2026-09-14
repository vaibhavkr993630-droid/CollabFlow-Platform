import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_project_role, require_workspace_role
from app.core.redis import get_redis_client
from app.crud import project as project_crud
from app.db.session import get_db
from app.models.project import Project, ProjectMembership
from app.models.roles import Role
from app.models.user import User
from app.schemas.project import (
    PresenceRead,
    ProjectCreate,
    ProjectMemberInvite,
    ProjectMemberRead,
    ProjectRead,
)
from app.services import project_service
from app.services.project_service import ProjectServiceError
from app.ws import presence

router = APIRouter(prefix="/api/workspaces/{workspace_id}/projects", tags=["projects"])
member_router = APIRouter(prefix="/api/projects/{project_id}", tags=["projects"])


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    workspace_id: uuid.UUID,
    project_in: ProjectCreate,
    current_user: User = Depends(require_workspace_role(Role.MEMBER)),
    db: AsyncSession = Depends(get_db),
) -> Project:
    try:
        return await project_service.create_project(
            db,
            workspace_id=workspace_id,
            name=project_in.name,
            description=project_in.description,
            creator_id=current_user.id,
        )
    except ProjectServiceError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("", response_model=list[ProjectRead])
async def list_projects(
    workspace_id: uuid.UUID,
    _: User = Depends(require_workspace_role(Role.MEMBER)),
    db: AsyncSession = Depends(get_db),
) -> list[Project]:
    return await project_crud.list_by_workspace(db, workspace_id=workspace_id)


@member_router.get("/members", response_model=list[ProjectMemberRead])
async def list_project_members(
    project_id: uuid.UUID,
    _: User = Depends(require_project_role(Role.MEMBER)),
    db: AsyncSession = Depends(get_db),
) -> list[ProjectMembership]:
    return await project_crud.list_members(db, project_id=project_id)


@member_router.post(
    "/members", response_model=ProjectMemberRead, status_code=status.HTTP_201_CREATED
)
async def invite_project_member(
    project_id: uuid.UUID,
    invite_in: ProjectMemberInvite,
    current_user: User = Depends(require_project_role(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ProjectMembership:
    try:
        return await project_service.invite_member(
            db,
            project_id=project_id,
            email=invite_in.email,
            role=invite_in.role,
            actor_id=current_user.id,
        )
    except ProjectServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@member_router.get("/presence", response_model=PresenceRead)
async def get_project_presence(
    project_id: uuid.UUID,
    _: User = Depends(require_project_role(Role.MEMBER)),
) -> PresenceRead:
    online_ids = await presence.online_user_ids(get_redis_client(), project_id=project_id)
    return PresenceRead(online_user_ids=online_ids)
