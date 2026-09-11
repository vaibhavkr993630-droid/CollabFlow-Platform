import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.slugs import slugify
from app.crud import organization as org_crud
from app.crud import user as user_crud
from app.crud import workspace as workspace_crud
from app.models.roles import Role
from app.models.workspace import Workspace, WorkspaceMembership


class WorkspaceServiceError(Exception):
    """Raised for not-found or invalid-state cases — mapped to 4xx at the router."""


async def create_workspace(
    db: AsyncSession, *, organization_id: uuid.UUID, name: str, creator_id: uuid.UUID
) -> Workspace:
    org = await org_crud.get_by_id(db, organization_id)
    if org is None:
        raise WorkspaceServiceError("Organization not found")

    workspace = await workspace_crud.create(
        db, name=name, slug=slugify(name), organization_id=organization_id
    )
    await workspace_crud.add_member(
        db, workspace_id=workspace.id, user_id=creator_id, role=Role.OWNER
    )
    await db.commit()
    await db.refresh(workspace)
    return workspace


async def invite_member(
    db: AsyncSession, *, workspace_id: uuid.UUID, email: str, role: Role
) -> WorkspaceMembership:
    user = await user_crud.get_by_email(db, email)
    if user is None:
        raise WorkspaceServiceError("No user found with that email")

    existing = await workspace_crud.get_membership(db, workspace_id=workspace_id, user_id=user.id)
    if existing is not None:
        raise WorkspaceServiceError("User is already a member of this workspace")

    membership = await workspace_crud.add_member(
        db, workspace_id=workspace_id, user_id=user.id, role=role
    )
    await db.commit()
    await db.refresh(membership)
    return membership
