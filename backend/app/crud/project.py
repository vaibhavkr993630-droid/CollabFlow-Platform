import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project, ProjectMembership
from app.models.roles import Role


async def get_by_id(db: AsyncSession, project_id: uuid.UUID) -> Project | None:
    return await db.get(Project, project_id)


async def create(
    db: AsyncSession, *, name: str, slug: str, description: str | None, workspace_id: uuid.UUID
) -> Project:
    project = Project(name=name, slug=slug, description=description, workspace_id=workspace_id)
    db.add(project)
    await db.flush()
    return project


async def add_member(
    db: AsyncSession, *, project_id: uuid.UUID, user_id: uuid.UUID, role: Role
) -> ProjectMembership:
    membership = ProjectMembership(project_id=project_id, user_id=user_id, role=role)
    db.add(membership)
    await db.flush()
    return membership


async def get_membership(
    db: AsyncSession, *, project_id: uuid.UUID, user_id: uuid.UUID
) -> ProjectMembership | None:
    result = await db.execute(
        select(ProjectMembership).where(
            ProjectMembership.project_id == project_id,
            ProjectMembership.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def list_members(db: AsyncSession, *, project_id: uuid.UUID) -> list[ProjectMembership]:
    result = await db.execute(
        select(ProjectMembership).where(ProjectMembership.project_id == project_id)
    )
    return list(result.scalars().all())


async def list_by_workspace(db: AsyncSession, *, workspace_id: uuid.UUID) -> list[Project]:
    result = await db.execute(select(Project).where(Project.workspace_id == workspace_id))
    return list(result.scalars().all())
