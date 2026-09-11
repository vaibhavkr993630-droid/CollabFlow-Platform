from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.crud import user as user_crud
from app.models.user import User
from app.schemas.auth import TokenPair
from app.schemas.user import UserCreate


class AuthError(Exception):
    """Raised for invalid credentials or tokens — mapped to 401 at the router."""


async def register_user(db: AsyncSession, user_in: UserCreate) -> User:
    existing = await user_crud.get_by_email(db, user_in.email)
    if existing is not None:
        raise AuthError("A user with this email already exists")
    return await user_crud.create(db, user_in)


async def authenticate(db: AsyncSession, email: str, password: str) -> User:
    user = await user_crud.get_by_email(db, email)
    if user is None or not verify_password(password, user.hashed_password):
        raise AuthError("Incorrect email or password")
    if not user.is_active:
        raise AuthError("User account is inactive")
    return user


def issue_token_pair(user: User) -> TokenPair:
    return TokenPair(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


async def refresh_access_token(db: AsyncSession, refresh_token: str) -> str:
    try:
        user_id = decode_token(refresh_token, TokenType.REFRESH)
    except Exception as exc:
        raise AuthError("Invalid or expired refresh token") from exc

    user = await user_crud.get_by_id(db, user_id)
    if user is None or not user.is_active:
        raise AuthError("User no longer active")

    return create_access_token(user.id)
