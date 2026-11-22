"""
Loads the sample project into a remote database and builds its search copies, from a laptop.

    cd backend && source .venv/bin/activate
    DATABASE_URL='postgresql+asyncpg://...neon.../db?ssl=require' \
    ASSISTANT_API_KEY='...' python -m scripts.prepare_live_demo --yes

Why a script: a free host has no background worker, so nothing would ever build the search
copies there. This builds them once, so smart search and "Ask" work on the sample project.
Anything written later on the live site is not searchable until this is run again.

Needs: the database migrated (`alembic upgrade head`), and a Redis on REDIS_URL that this
machine can reach (the local one from `docker compose up -d redis` is fine; the live site's own
Redis is not needed here). Safe to run twice.
"""

import argparse
import asyncio
import sys
from urllib.parse import urlsplit

from sqlalchemy import text

from app.assistant import indexing
from app.assistant.deps import get_assistant_client
from app.core.config import get_settings
from app.db.session import AsyncSessionLocal, engine
from scripts import seed_sample_project

MAX_ROUNDS = 10  # each round indexes up to 200 items; the sample project needs one


async def main(confirmed: bool) -> int:
    settings = get_settings()
    host = urlsplit(settings.database_url.replace("+asyncpg", "")).hostname
    print(f"Target database host: {host}")
    if not confirmed:
        print("Add --yes to continue. Nothing was changed.")
        return 2

    async with AsyncSessionLocal() as db:
        migrated = await db.scalar(text("SELECT version_num FROM alembic_version"))
        ready = await indexing.is_ready(db)
    print(f"Database migration version: {migrated}")
    if not ready:
        print("The database has no search table. Run `alembic upgrade head` against it first,")
        print("and check that its Postgres has the pgvector extension.")
        return 1

    client = get_assistant_client()
    if client is None:
        print("ASSISTANT_API_KEY is not set: sample data will be loaded, but not indexed.")

    await seed_sample_project.main()

    if client is not None:
        total = 0
        async with AsyncSessionLocal() as db:
            for _ in range(MAX_ROUNDS):
                sent = await indexing.reindex_stale(db, client, limit=200)
                total += sent
                if sent == 0:
                    break
        print(f"Search copies built or refreshed: {total}")
    await engine.dispose()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--yes", action="store_true", help="confirm the target database")
    sys.exit(asyncio.run(main(parser.parse_args().yes)))
