"""The server must start on hosts that have no file storage (attachments simply do not work)."""

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.db.session import get_db
from tests.conftest import TestSessionLocal


def test_app_starts_when_file_storage_is_down(monkeypatch: pytest.MonkeyPatch):
    def storage_is_down() -> None:
        raise RuntimeError("no object storage on this host")

    monkeypatch.setattr(main_module, "ensure_bucket_exists", storage_is_down)

    async def _test_db():
        async with TestSessionLocal() as session:
            yield session

    main_module.app.dependency_overrides[get_db] = _test_db
    try:
        with TestClient(main_module.app) as client:  # startup runs here and must not raise
            assert client.get("/health").status_code == 200
    finally:
        main_module.app.dependency_overrides.clear()
