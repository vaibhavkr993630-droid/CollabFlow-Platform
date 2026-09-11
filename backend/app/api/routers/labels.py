import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_project_role
from app.crud import label as label_crud
from app.db.session import get_db
from app.models.label import Label
from app.models.roles import Role
from app.models.user import User
from app.schemas.label import LabelCreate, LabelRead
from app.services import label_service
from app.services.label_service import LabelServiceError

router = APIRouter(prefix="/api/projects/{project_id}/labels", tags=["labels"])


@router.post("", response_model=LabelRead, status_code=status.HTTP_201_CREATED)
async def create_label(
    project_id: uuid.UUID,
    label_in: LabelCreate,
    _: User = Depends(require_project_role(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> Label:
    try:
        return await label_service.create_label(
            db, project_id=project_id, name=label_in.name, color=label_in.color
        )
    except LabelServiceError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("", response_model=list[LabelRead])
async def list_labels(
    project_id: uuid.UUID,
    _: User = Depends(require_project_role(Role.MEMBER)),
    db: AsyncSession = Depends(get_db),
) -> list[Label]:
    return await label_crud.list_by_project(db, project_id=project_id)
