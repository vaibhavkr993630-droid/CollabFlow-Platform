import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"
    PASSWORD_RESET = "password_reset"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def _create_token(subject: UUID, token_type: TokenType, expires_delta: timedelta) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(subject),
        "type": token_type.value,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: UUID) -> str:
    return _create_token(
        user_id, TokenType.ACCESS, timedelta(minutes=settings.access_token_expire_minutes)
    )


def create_refresh_token(user_id: UUID) -> str:
    return _create_token(
        user_id, TokenType.REFRESH, timedelta(days=settings.refresh_token_expire_days)
    )


class InvalidTokenError(Exception):
    pass


def _decode_payload(token: str, expected_type: TokenType) -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise InvalidTokenError("Could not validate token") from exc

    if payload.get("type") != expected_type.value:
        raise InvalidTokenError(f"Expected a {expected_type.value} token")

    if payload.get("sub") is None:
        raise InvalidTokenError("Token missing subject")

    return payload


def decode_token(token: str, expected_type: TokenType) -> UUID:
    return UUID(_decode_payload(token, expected_type)["sub"])


def password_fingerprint(hashed_password: str) -> str:
    """
    A short, non-reversible marker of "which password this account has right now".
    bcrypt salts every hash, so it changes on every password change — even to the
    same plaintext.
    """
    return hashlib.sha256(hashed_password.encode()).hexdigest()[:32]


def fingerprints_match(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)


def create_password_reset_token(
    user_id: UUID, hashed_password: str, expires_delta: timedelta | None = None
) -> str:
    """
    Stateless reset token — no table, no migration. It embeds a fingerprint of the
    user's *current* password hash, so it stops working the moment the password
    changes: single-use without having to store anything. The fingerprint travels
    inside the signed token, so it can't be forged or swapped.
    """
    now = datetime.now(UTC)
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.password_reset_expire_minutes)
    payload = {
        "sub": str(user_id),
        "type": TokenType.PASSWORD_RESET.value,
        "pwd": password_fingerprint(hashed_password),
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_password_reset_token(token: str) -> tuple[UUID, str]:
    payload = _decode_payload(token, TokenType.PASSWORD_RESET)
    fingerprint = payload.get("pwd")
    if not isinstance(fingerprint, str):
        raise InvalidTokenError("Token missing password fingerprint")
    return UUID(payload["sub"]), fingerprint
