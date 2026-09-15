import uuid

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.slugs import slugify
from app.crud import project as project_crud
from app.crud import user as user_crud
from app.crud import workspace as workspace_crud
from app.models.activity import ActivityAction
from app.models.notification import NotificationType
from app.models.project import Project, ProjectMembership
from app.models.roles import Role
from app.services import activity_service, notification_service


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
    await project_crud.add_member(db, project_id=project.id, user_id=creator_id, role=Role.OWNER)
    await activity_service.log(
        db,
        project_id=project.id,
        actor_id=creator_id,
        action=ActivityAction.PROJECT_CREATED,
        summary=f"created project '{name}'",
    )
    await db.commit()
    await db.refresh(project)
    return project


async def invite_member(
    db: AsyncSession,
    redis: Redis,
    *,
    project_id: uuid.UUID,
    email: str,
    role: Role,
    actor_id: uuid.UUID,
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
    await activity_service.log(
        db,
        project_id=project_id,
        actor_id=actor_id,
        action=ActivityAction.MEMBER_INVITED,
        summary=f"invited {email} as {role.value}",
    )
    await db.commit()
    await db.refresh(membership)

    project = await project_crud.get_by_id(db, project_id)
    await notification_service.create_and_dispatch(
        db,
        redis,
        user_id=user.id,
        type=NotificationType.PROJECT_INVITE,
        title=f"You were added to project '{project.name}'",
        body=f"You were added to project '{project.name}' as {role.value}.",
        project_id=project_id,
    )
    return membership
