import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.slugs import slugify
from app.crud import organization as org_crud
from app.crud import workspace as workspace_crud
from app.models.organization import Organization
from app.models.roles import Role


async def _unique_org_slug(db: AsyncSession, base: str) -> str:
    slug = slugify(base)
    candidate = slug
    suffix = 1
    while (
        await db.execute(select(Organization).where(Organization.slug == candidate))
    ).scalar_one_or_none() is not None:
        suffix += 1
        candidate = f"{slug}-{suffix}"
    return candidate


async def create_organization_with_owner(
    db: AsyncSession, *, name: str, owner_id: uuid.UUID
) -> Organization:
    """Creates an org and a default 'General' workspace, seeding the creator as owner of both."""
    slug = await _unique_org_slug(db, name)
    org = await org_crud.create(db, name=name, slug=slug, owner_id=owner_id)

    workspace = await workspace_crud.create(
        db, name="General", slug="general", organization_id=org.id
    )
    await workspace_crud.add_member(
        db, workspace_id=workspace.id, user_id=owner_id, role=Role.OWNER
    )
    await db.commit()
    await db.refresh(org)
    return org
