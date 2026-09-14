from collections.abc import AsyncGenerator, Generator

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.redis import close_redis_client
from app.db.base import Base
from app.db.session import get_db
from app.main import app

settings = get_settings()

# NullPool: pytest-asyncio opens a fresh event loop per test function, but pooled
# asyncpg connections are bound to the loop they were created on — a pooled connection
# reused across loops raises "another operation is in progress". NullPool opens a new
# connection per checkout instead of reusing one across tests.
engine = create_async_engine(settings.test_database_url, future=True, poolclass=NullPool)
TestSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(autouse=True)
async def _reset_schema() -> AsyncGenerator[None, None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest.fixture(autouse=True)
async def _reset_redis_client() -> AsyncGenerator[None, None]:
    """
    get_redis_client() is a process-wide singleton (see app/core/redis.py) — fine
    in production (one event loop for the process's whole lifetime), but
    pytest-asyncio hands each test function its own event loop. A redis-py client
    created under test A's loop breaks with "Event loop is closed" once test B's
    (different) loop tries to use it. Same root cause NullPool fixes for the DB
    engine above; the fix here is closing it after every test so the next test
    creates its own, bound to its own loop.
    """
    yield
    await close_redis_client()


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionLocal() as session:
        yield session


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    async def _get_test_db() -> AsyncGenerator[AsyncSession, None]:
        async with TestSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = _get_test_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def ws_client() -> Generator[TestClient, None, None]:
    """
    For WebSocket tests only: httpx.AsyncClient has no WebSocket support, so this
    uses Starlette's synchronous TestClient instead (FastAPI's own recommended way
    to test WebSocket routes). It runs the ASGI app in a background thread with its
    own event loop; our async DB engine uses NullPool (see `engine` above), so a
    connection opened from that thread is never reused across event loops — the
    same reasoning that made NullPool necessary for the async fixtures.
    """

    async def _get_test_db() -> AsyncGenerator[AsyncSession, None]:
        async with TestSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = _get_test_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
