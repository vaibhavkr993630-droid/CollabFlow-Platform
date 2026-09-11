import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_workspace_role
from app.crud import workspace as workspace_crud
from app.db.session import get_db
from app.models.roles import Role
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMembership
from app.schemas.workspace import (
    WorkspaceCreate,
    WorkspaceMemberInvite,
    WorkspaceMemberRead,
    WorkspaceRead,
)
from app.services import workspace_service
from app.services.workspace_service import WorkspaceServiceError

router = APIRouter(prefix="/api/organizations/{organization_id}/workspaces", tags=["workspaces"])
member_router = APIRouter(prefix="/api/workspaces/{workspace_id}", tags=["workspaces"])


@router.post("", response_model=WorkspaceRead, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    organization_id: uuid.UUID,
    workspace_in: WorkspaceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Workspace:
    try:
        return await workspace_service.create_workspace(
            db,
            organization_id=organization_id,
            name=workspace_in.name,
            creator_id=current_user.id,
        )
    except WorkspaceServiceError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@member_router.get("/members", response_model=list[WorkspaceMemberRead])
async def list_workspace_members(
    workspace_id: uuid.UUID,
    _: User = Depends(require_workspace_role(Role.MEMBER)),
    db: AsyncSession = Depends(get_db),
) -> list[WorkspaceMembership]:
    return await workspace_crud.list_members(db, workspace_id=workspace_id)


@member_router.post(
    "/members", response_model=WorkspaceMemberRead, status_code=status.HTTP_201_CREATED
)
async def invite_workspace_member(
    workspace_id: uuid.UUID,
    invite_in: WorkspaceMemberInvite,
    _: User = Depends(require_workspace_role(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceMembership:
    try:
        return await workspace_service.invite_member(
            db, workspace_id=workspace_id, email=invite_in.email, role=invite_in.role
        )
    except WorkspaceServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
