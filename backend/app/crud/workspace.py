import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workspace import Workspace, WorkspaceMembership, WorkspaceRole


async def get_by_id(db: AsyncSession, workspace_id: uuid.UUID) -> Workspace | None:
    return await db.get(Workspace, workspace_id)


async def create(
    db: AsyncSession, *, name: str, slug: str, organization_id: uuid.UUID
) -> Workspace:
    workspace = Workspace(name=name, slug=slug, organization_id=organization_id)
    db.add(workspace)
    await db.flush()
    return workspace


async def add_member(
    db: AsyncSession, *, workspace_id: uuid.UUID, user_id: uuid.UUID, role: WorkspaceRole
) -> WorkspaceMembership:
    membership = WorkspaceMembership(workspace_id=workspace_id, user_id=user_id, role=role)
    db.add(membership)
    await db.flush()
    return membership


async def get_membership(
    db: AsyncSession, *, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> WorkspaceMembership | None:
    result = await db.execute(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def list_members(db: AsyncSession, *, workspace_id: uuid.UUID) -> list[WorkspaceMembership]:
    result = await db.execute(
        select(WorkspaceMembership).where(WorkspaceMembership.workspace_id == workspace_id)
    )
    return list(result.scalars().all())
