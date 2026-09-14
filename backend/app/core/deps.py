import uuid

from fastapi import Depends, HTTPException, Path, Query, WebSocketException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import InvalidTokenError, TokenType, decode_token
from app.crud import project as project_crud
from app.crud import task as task_crud
from app.crud import user as user_crud
from app.crud import workspace as workspace_crud
from app.db.session import get_db
from app.models.roles import ROLE_RANK, Role
from app.models.task import Task
from app.models.user import User

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


def require_ws_project_role(min_role: Role):
    """
    WebSocket equivalent of require_project_role, resolved as a normal FastAPI
    Depends() rather than called by hand: raising WebSocketException from a
    dependency makes FastAPI close the socket with that code *before* accepting
    the connection, so this plugs into Depends(get_db) like every HTTP dependency
    instead of needing a hand-rolled DB session that tests can't override.

    Token arrives as a query parameter (`?token=...`), not an Authorization header
    — browsers' native WebSocket API cannot set custom headers on the handshake
    request. Real tradeoff: a short-lived access token ends up in server access
    logs via the query string. Documented in PROGRESS.md under Known
    Simplifications; a production system would issue a short-lived, single-use WS
    ticket via an authenticated REST call instead of reusing the access token here.
    """

    async def _check(
        project_id: uuid.UUID = Path(...),
        token: str = Query(...),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        try:
            user_id = decode_token(token, TokenType.ACCESS)
        except InvalidTokenError as exc:
            raise WebSocketException(code=4401, reason="Invalid or expired token") from exc

        user = await user_crud.get_by_id(db, user_id)
        if user is None or not user.is_active:
            raise WebSocketException(code=4401, reason="Invalid or expired token")

        membership = await project_crud.get_membership(db, project_id=project_id, user_id=user.id)
        if membership is None or ROLE_RANK[membership.role] < ROLE_RANK[min_role]:
            raise WebSocketException(code=4403, reason="Not a member of this project")

        return user

    return _check


def require_workspace_role(min_role: Role):
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


def require_project_role(min_role: Role):
    """
    Same idea as require_workspace_role, but checks membership in the project
    identified by the `project_id` path parameter. Project and workspace roles are
    independent — a workspace Owner is not automatically a member of every project.
    """

    async def _check(
        project_id: uuid.UUID = Path(...),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        membership = await project_crud.get_membership(
            db, project_id=project_id, user_id=current_user.id
        )
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not a member of this project",
            )
        if ROLE_RANK[membership.role] < ROLE_RANK[min_role]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires at least '{min_role.value}' role in this project",
            )
        return current_user

    return _check


def require_task_project_role(min_role: Role):
    """
    For routes keyed on `task_id` rather than `project_id` (task detail, comments,
    subtasks): loads the task, then checks the current user's role in *its* project.
    Returns the loaded Task so route handlers don't need to re-fetch it.
    """

    async def _check(
        task_id: uuid.UUID = Path(...),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> Task:
        task = await task_crud.get_by_id(db, task_id)
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

        membership = await project_crud.get_membership(
            db, project_id=task.project_id, user_id=current_user.id
        )
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not a member of this task's project",
            )
        if ROLE_RANK[membership.role] < ROLE_RANK[min_role]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires at least '{min_role.value}' role in this project",
            )
        return task

    return _check
