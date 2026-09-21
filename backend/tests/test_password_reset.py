import re
from datetime import timedelta
from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_password_reset_token
from app.models.user import User
from app.workers import tasks as worker_tasks

pytestmark = pytest.mark.asyncio

EMAIL = "forgetful@example.com"
OLD_PASSWORD = "oldpassword1"
NEW_PASSWORD = "brandnewpass2"


@pytest.fixture
def sent_emails(monkeypatch) -> list[dict]:
    """Captures what would have been queued for Celery instead of really queueing it."""
    sent: list[dict] = []

    def fake_delay(to_email: str, subject: str, body: str) -> None:
        sent.append({"to": to_email, "subject": subject, "body": body})

    monkeypatch.setattr(
        worker_tasks, "send_notification_email", SimpleNamespace(delay=fake_delay)
    )
    return sent


async def _register(client: AsyncClient, email: str = EMAIL) -> None:
    resp = await client.post(
        "/api/auth/register",
        json={"email": email, "password": OLD_PASSWORD, "full_name": "Forgetful User"},
    )
    assert resp.status_code == 201


async def _login_status(client: AsyncClient, password: str, email: str = EMAIL) -> int:
    resp = await client.post("/api/auth/login", json={"email": email, "password": password})
    return resp.status_code


async def _request_reset_token(client: AsyncClient, sent_emails: list[dict]) -> str:
    resp = await client.post("/api/auth/forgot-password", json={"email": EMAIL})
    assert resp.status_code == 200
    match = re.search(r"token=([\w.\-]+)", sent_emails[-1]["body"])
    assert match, "the email should contain a reset link with a token"
    return match.group(1)


async def _user(db_session: AsyncSession, email: str = EMAIL) -> User:
    return (await db_session.execute(select(User).where(User.email == email))).scalar_one()


async def test_forgot_password_emails_a_link_for_a_real_account(
    client: AsyncClient, sent_emails: list[dict]
):
    await _register(client)

    resp = await client.post("/api/auth/forgot-password", json={"email": EMAIL})

    assert resp.status_code == 200
    assert len(sent_emails) == 1
    assert sent_emails[0]["to"] == EMAIL
    assert "/reset-password?token=" in sent_emails[0]["body"]


async def test_forgot_password_gives_the_same_answer_for_unknown_emails(
    client: AsyncClient, sent_emails: list[dict]
):
    await _register(client)

    known = await client.post("/api/auth/forgot-password", json={"email": EMAIL})
    unknown = await client.post("/api/auth/forgot-password", json={"email": "nobody@example.com"})

    # Identical status *and* body — otherwise the endpoint reveals who has an account.
    assert unknown.status_code == known.status_code == 200
    assert unknown.json() == known.json()
    # ...and nothing was sent to the address that has no account.
    assert [e["to"] for e in sent_emails] == [EMAIL]


async def test_forgot_password_rejects_a_malformed_email(client: AsyncClient):
    resp = await client.post("/api/auth/forgot-password", json={"email": "not-an-email"})
    assert resp.status_code == 422


async def test_reset_password_changes_the_password(client: AsyncClient, sent_emails: list[dict]):
    await _register(client)
    token = await _request_reset_token(client, sent_emails)

    resp = await client.post(
        "/api/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD}
    )

    assert resp.status_code == 200
    assert await _login_status(client, NEW_PASSWORD) == 200
    assert await _login_status(client, OLD_PASSWORD) == 401


async def test_reset_link_only_works_once(client: AsyncClient, sent_emails: list[dict]):
    await _register(client)
    token = await _request_reset_token(client, sent_emails)

    first = await client.post(
        "/api/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD}
    )
    second = await client.post(
        "/api/auth/reset-password", json={"token": token, "new_password": "anotherpass3"}
    )

    assert first.status_code == 200
    assert second.status_code == 400
    # The second attempt must not have changed anything.
    assert await _login_status(client, NEW_PASSWORD) == 200
    assert await _login_status(client, "anotherpass3") == 401


async def test_reset_rejects_a_garbage_token(client: AsyncClient):
    resp = await client.post(
        "/api/auth/reset-password",
        json={"token": "definitely.not.valid", "new_password": NEW_PASSWORD},
    )
    assert resp.status_code == 400


async def test_an_access_token_cannot_be_used_to_reset_a_password(client: AsyncClient):
    await _register(client)
    login = await client.post("/api/auth/login", json={"email": EMAIL, "password": OLD_PASSWORD})
    access_token = login.json()["access_token"]

    resp = await client.post(
        "/api/auth/reset-password", json={"token": access_token, "new_password": NEW_PASSWORD}
    )

    assert resp.status_code == 400
    assert await _login_status(client, OLD_PASSWORD) == 200


async def test_reset_rejects_an_expired_token(client: AsyncClient, db_session: AsyncSession):
    await _register(client)
    user = await _user(db_session)
    expired = create_password_reset_token(
        user.id, user.hashed_password, expires_delta=timedelta(minutes=-1)
    )

    resp = await client.post(
        "/api/auth/reset-password", json={"token": expired, "new_password": NEW_PASSWORD}
    )

    assert resp.status_code == 400
    assert await _login_status(client, OLD_PASSWORD) == 200


async def test_reset_rejects_a_too_short_password(client: AsyncClient, sent_emails: list[dict]):
    await _register(client)
    token = await _request_reset_token(client, sent_emails)

    resp = await client.post(
        "/api/auth/reset-password", json={"token": token, "new_password": "short"}
    )

    assert resp.status_code == 422
    assert await _login_status(client, OLD_PASSWORD) == 200


async def test_inactive_accounts_get_no_email_and_cannot_reset(
    client: AsyncClient, db_session: AsyncSession, sent_emails: list[dict]
):
    await _register(client)
    user = await _user(db_session)
    token = create_password_reset_token(user.id, user.hashed_password)
    await db_session.execute(update(User).where(User.email == EMAIL).values(is_active=False))
    await db_session.commit()

    forgot = await client.post("/api/auth/forgot-password", json={"email": EMAIL})
    reset = await client.post(
        "/api/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD}
    )

    assert forgot.status_code == 200
    assert sent_emails == []
    assert reset.status_code == 400
