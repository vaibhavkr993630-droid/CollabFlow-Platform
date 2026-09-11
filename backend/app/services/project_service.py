import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.slugs import slugify
from app.crud import project as project_crud
from app.crud import user as user_crud
from app.crud import workspace as workspace_crud
from app.models.project import Project, ProjectMembership
from app.models.roles import Role


class ProjectServiceError(Exception):
    """Raised for not-found or invalid-state cases — mapped to 4xx at the router."""


async def create_project(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    name: str,
    description: str | None,
    creator_id: uuid.UUID,
) -> Project:
    workspace = await workspace_crud.get_by_id(db, workspace_id)
    if workspace is None:
        raise ProjectServiceError("Workspace not found")

    project = await project_crud.create(
        db, name=name, slug=slugify(name), description=description, workspace_id=workspace_id
    )
    await project_crud.add_member(
        db, project_id=project.id, user_id=creator_id, role=Role.OWNER
    )
    await db.commit()
    await db.refresh(project)
    return project


async def invite_member(
    db: AsyncSession, *, project_id: uuid.UUID, email: str, role: Role
) -> ProjectMembership:
    user = await user_crud.get_by_email(db, email)
    if user is None:
        raise ProjectServiceError("No user found with that email")

    existing = await project_crud.get_membership(db, project_id=project_id, user_id=user.id)
    if existing is not None:
        raise ProjectServiceError("User is already a member of this project")

    membership = await project_crud.add_member(
        db, project_id=project_id, user_id=user.id, role=role
    )
    await db.commit()
    await db.refresh(membership)
    return membership
