import uuid

from fastapi import Depends, HTTPException, Path, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import InvalidTokenError, TokenType, decode_token
from app.crud import user as user_crud
from app.crud import workspace as workspace_crud
from app.db.session import get_db
from app.models.user import User
from app.models.workspace import ROLE_RANK, WorkspaceRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        user_id = decode_token(token, TokenType.ACCESS)
    except InvalidTokenError as exc:
        raise credentials_error from exc

    user = await user_crud.get_by_id(db, user_id)
    if user is None or not user.is_active:
        raise credentials_error
    return user


def require_workspace_role(min_role: WorkspaceRole):
    """
    Returns a FastAPI dependency that ensures the current user is a member of the
    workspace identified by the `workspace_id` path parameter, with at least
    `min_role` privilege. Centralizing this as a dependency (rather than inline
    `if` checks in routers) keeps permission logic reusable and testable in isolation.
    """

    async def _check(
        workspace_id: uuid.UUID = Path(...),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        membership = await workspace_crud.get_membership(
            db, workspace_id=workspace_id, user_id=current_user.id
        )
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not a member of this workspace",
            )
        if ROLE_RANK[membership.role] < ROLE_RANK[min_role]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires at least '{min_role.value}' role in this workspace",
            )
        return current_user

    return _check
