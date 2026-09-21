FROM python:3.12-slim AS base

WORKDIR /app

# System deps for psycopg/asyncpg builds and healthchecks — kept minimal
# deliberately, this isn't a build stage that needs a full toolchain.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./

# Editable install would need the dev-only tests/ dir excluded from the image;
# a regular install is simpler and correct for a runtime image that never
# needs to re-resolve the package after code changes (those come via rebuild).
RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
