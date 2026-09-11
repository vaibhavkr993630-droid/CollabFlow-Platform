import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization


async def get_by_id(db: AsyncSession, org_id: uuid.UUID) -> Organization | None:
    return await db.get(Organization, org_id)


async def create(db: AsyncSession, *, name: str, slug: str, owner_id: uuid.UUID) -> Organization:
    org = Organization(name=name, slug=slug, owner_id=owner_id)
    db.add(org)
    await db.flush()
    return org
