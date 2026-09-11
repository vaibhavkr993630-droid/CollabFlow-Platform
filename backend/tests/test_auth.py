import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _register(client: AsyncClient, email: str = "jane@example.com") -> dict:
    resp = await client.post(
        "/api/auth/register",
        json={"email": email, "password": "supersecret1", "full_name": "Jane Doe"},
    )
    assert resp.status_code == 201
    return resp.json()


async def test_register_creates_user(client: AsyncClient):
    body = await _register(client)
    assert body["email"] == "jane@example.com"
    assert "id" in body
    assert "hashed_password" not in body


async def test_register_duplicate_email_rejected(client: AsyncClient):
    await _register(client)
    resp = await client.post(
        "/api/auth/register",
        json={"email": "jane@example.com", "password": "supersecret1", "full_name": "Jane"},
    )
    assert resp.status_code == 409


async def test_login_success_returns_token_pair(client: AsyncClient):
    await _register(client)
    resp = await client.post(
        "/api/auth/login", json={"email": "jane@example.com", "password": "supersecret1"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"


async def test_login_wrong_password_rejected(client: AsyncClient):
    await _register(client)
    resp = await client.post(
        "/api/auth/login", json={"email": "jane@example.com", "password": "wrongpass"}
    )
    assert resp.status_code == 401


async def test_me_requires_valid_token(client: AsyncClient):
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401

    await _register(client)
    login = await client.post(
        "/api/auth/login", json={"email": "jane@example.com", "password": "supersecret1"}
    )
    token = login.json()["access_token"]
    resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "jane@example.com"


async def test_refresh_issues_new_access_token(client: AsyncClient):
    await _register(client)
    login = await client.post(
        "/api/auth/login", json={"email": "jane@example.com", "password": "supersecret1"}
    )
    refresh_token = login.json()["refresh_token"]

    resp = await client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    assert resp.json()["access_token"]


async def test_refresh_rejects_access_token(client: AsyncClient):
    await _register(client)
    login = await client.post(
        "/api/auth/login", json={"email": "jane@example.com", "password": "supersecret1"}
    )
    access_token = login.json()["access_token"]

    resp = await client.post("/api/auth/refresh", json={"refresh_token": access_token})
    assert resp.status_code == 401
