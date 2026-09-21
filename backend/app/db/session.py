from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()

# echo=False always, even in debug mode: SQLAlchemy's echo=True attaches its own
# StreamHandler to the sqlalchemy.engine logger *in addition to* propagating to
# root, which duplicated every SQL log line (once plain-text from SQLAlchemy's
# own handler, once as JSON from app.core.logging_config's root handler) once
# structured logging was wired up. To see SQL locally, set the sqlalchemy.engine
# logger to INFO directly instead — it'll flow through the one JSON handler.
engine = create_async_engine(settings.database_url, echo=False, future=True)

AsyncSessionLocal = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
