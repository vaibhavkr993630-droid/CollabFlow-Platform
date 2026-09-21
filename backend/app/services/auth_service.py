from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import (
    InvalidTokenError,
    TokenType,
    create_access_token,
    create_refresh_token,
    create_password_reset_token,
    decode_password_reset_token,
    decode_token,
    fingerprints_match,
    password_fingerprint,
    verify_password,
)
from app.crud import user as user_crud
from app.models.user import User
from app.schemas.auth import TokenPair
from app.schemas.user import UserCreate

settings = get_settings()


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


_INVALID_RESET_LINK = "This password reset link is invalid or has expired"


async def request_password_reset(db: AsyncSession, email: str) -> None:
    """
    Emails a reset link if — and only if — an active account has this address.
    Returns nothing either way, on purpose: the caller (and so the HTTP response)
    must not reveal whether an email is registered, or this endpoint becomes a way
    to probe which people have accounts.
    """
    user = await user_crud.get_by_email(db, email)
    if user is None or not user.is_active:
        return

    token = create_password_reset_token(user.id, user.hashed_password)
    link = f"{settings.frontend_url.rstrip('/')}/reset-password?token={token}"
    body = (
        f"Hi {user.full_name},\n\n"
        "We received a request to reset your CollabFlow password. Open the link below to "
        f"choose a new one. It works once and expires in {settings.password_reset_expire_minutes} "
        "minutes:\n\n"
        f"{link}\n\n"
        "If you didn't ask for this, you can ignore this email — your password will not change."
    )

    # Imported here, not at module level: same reasoning as notification_service — the API
    # process shouldn't load Celery's app registration just to import this module.
    from app.workers.tasks import send_notification_email

    send_notification_email.delay(user.email, "Reset your CollabFlow password", body)


async def reset_password(db: AsyncSession, token: str, new_password: str) -> None:
    try:
        user_id, fingerprint = decode_password_reset_token(token)
    except InvalidTokenError as exc:
        raise AuthError(_INVALID_RESET_LINK) from exc

    user = await user_crud.get_by_id(db, user_id)
    # The fingerprint check is what makes a link single-use: once the password has
    # changed, the hash it was minted against no longer exists.
    if (
        user is None
        or not user.is_active
        or not fingerprints_match(password_fingerprint(user.hashed_password), fingerprint)
    ):
        raise AuthError(_INVALID_RESET_LINK)

    await user_crud.set_password(db, user, new_password)
