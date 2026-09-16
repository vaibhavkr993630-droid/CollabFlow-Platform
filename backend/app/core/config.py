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

    # File storage (MinIO locally, any S3-compatible endpoint in production)
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "collabflow"
    s3_secret_key: str = "collabflow123"
    s3_bucket: str = "collabflow-attachments"
    max_attachment_size_mb: int = 10

    # CORS
    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
