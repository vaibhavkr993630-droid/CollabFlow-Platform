from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    app_name: str = "CollabFlow"
    environment: str = "development"
    debug: bool = True

    # Database
    database_url: str = "postgresql+asyncpg://collabflow:collabflow@localhost:5432/collabflow"
    test_database_url: str = (
        "postgresql+asyncpg://collabflow:collabflow@localhost:5432/collabflow_test"
    )

    # Auth
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Email (Celery worker; MailDev in local dev — see docker-compose.yml)
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_from: str = "noreply@collabflow.local"

    # File storage (MinIO locally, any S3-compatible endpoint in production).
    # s3_endpoint_url is what the backend itself uses to talk to the bucket
    # (put/get/delete/head) — inside Docker Compose this is the internal service
    # name (http://minio:9000). s3_public_endpoint_url is what gets baked into
    # presigned URLs handed back to *external* clients (a browser, curl from the
    # host) — those can't resolve "minio" as a hostname, they need the
    # host-mapped address (http://localhost:9000 locally; a real public domain
    # in production). Defaults to s3_endpoint_url when unset, which is correct
    # for the non-Docker local dev flow where both already point at localhost.
    s3_endpoint_url: str = "http://localhost:9000"
    s3_public_endpoint_url: str | None = None
    s3_access_key: str = "collabflow"
    s3_secret_key: str = "collabflow123"
    s3_bucket: str = "collabflow-attachments"
    max_attachment_size_mb: int = 10

    # Error tracking — unset (default) means Sentry is never initialized; the app
    # runs identically either way. Only set this once you have a Sentry project.
    sentry_dsn: str | None = None

    # CORS
    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
