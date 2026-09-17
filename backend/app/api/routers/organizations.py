from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.crud import organization as organization_crud
from app.db.session import get_db
from app.models.organization import Organization
from app.models.user import User
from app.schemas.organization import OrganizationCreate, OrganizationRead
from app.services import organization_service

router = APIRouter(prefix="/api/organizations", tags=["organizations"])


@router.post("", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED)
async def create_organization(
    org_in: OrganizationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    return await organization_service.create_organization_with_owner(
        db, name=org_in.name, owner_id=current_user.id
    )


@router.get("", response_model=list[OrganizationRead])
async def list_organizations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Organization]:
    """
    No dedicated org-membership table exists — see
    organization_crud.list_for_user's docstring for what "belongs to" means
    here (owns it, or is a member of at least one of its workspaces).
    """
    return await organization_crud.list_for_user(db, user_id=current_user.id)
