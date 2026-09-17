import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.models.workspace import Workspace, WorkspaceMembership


async def get_by_id(db: AsyncSession, org_id: uuid.UUID) -> Organization | None:
    return await db.get(Organization, org_id)


async def create(db: AsyncSession, *, name: str, slug: str, owner_id: uuid.UUID) -> Organization:
    org = Organization(name=name, slug=slug, owner_id=owner_id)
    db.add(org)
    await db.flush()
    return org


async def list_for_user(db: AsyncSession, *, user_id: uuid.UUID) -> list[Organization]:
    """
    Organizations aren't membership-modeled directly — a user "belongs to" one
    either by owning it, or by being a member of at least one of its workspaces
    (invited in). Returns the union of both, deduplicated.

    Deliberately two queries merged in Python, not select(Organization).union(...):
    SQLAlchemy's .union() on ORM-entity selects produces a Core-level compound
    select that does NOT preserve entity mapping — .scalars() on the result
    silently returns raw first-column values (here, org names as bare strings)
    instead of Organization objects. Caught by a ResponseValidationError in a
    test, not by anything that looked wrong in the query itself.
    """
    owned_result = await db.execute(select(Organization).where(Organization.owner_id == user_id))
    via_workspace_result = await db.execute(
        select(Organization)
        .join(Workspace, Workspace.organization_id == Organization.id)
        .join(WorkspaceMembership, WorkspaceMembership.workspace_id == Workspace.id)
        .where(WorkspaceMembership.user_id == user_id)
    )
    by_id = {org.id: org for org in owned_result.scalars().all()}
    for org in via_workspace_result.scalars().all():
        by_id.setdefault(org.id, org)
    return list(by_id.values())
