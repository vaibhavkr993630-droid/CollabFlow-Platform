import pytest
from botocore.exceptions import ClientError
from httpx import AsyncClient

from app.core.config import get_settings
from app.core.storage import get_s3_client
from app.crud import attachment as attachment_crud
from app.services import attachment_service
from tests.helpers import (
    auth_headers,
    create_org_and_workspace,
    create_project,
    register_and_login,
)

pytestmark = pytest.mark.asyncio


async def _setup_task(client: AsyncClient) -> tuple[str, str, str]:
    """Registers an owner, creates org/workspace/project/task, returns
    (owner_token, project_id, task_id)."""
    token, _ = await register_and_login(client, "attachowner@example.com", "Owner")
    _, workspace_id = await create_org_and_workspace(client, token, "Acme")
    project_id = await create_project(client, token, workspace_id)
    task_resp = await client.post(
        f"/api/projects/{project_id}/tasks",
        json={"title": "Task with files"},
        headers=auth_headers(token),
    )
    return token, project_id, task_resp.json()["id"]


async def test_upload_and_list_attachment(client: AsyncClient):
    token, _, task_id = await _setup_task(client)

    resp = await client.post(
        f"/api/tasks/{task_id}/attachments",
        files={"file": ("notes.txt", b"hello world", "text/plain")},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["filename"] == "notes.txt"
    assert body["size_bytes"] == 11
    assert body["content_type"] == "text/plain"

    listed = await client.get(f"/api/tasks/{task_id}/attachments", headers=auth_headers(token))
    assert listed.status_code == 200
    assert len(listed.json()) == 1


async def test_upload_empty_file_rejected(client: AsyncClient):
    token, _, task_id = await _setup_task(client)

    resp = await client.post(
        f"/api/tasks/{task_id}/attachments",
        files={"file": ("empty.txt", b"", "text/plain")},
        headers=auth_headers(token),
    )
    assert resp.status_code == 400


async def test_upload_oversized_file_rejected(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(attachment_service.settings, "max_attachment_size_mb", 0)
    token, _, task_id = await _setup_task(client)

    resp = await client.post(
        f"/api/tasks/{task_id}/attachments",
        files={"file": ("big.txt", b"x" * 1024, "text/plain")},
        headers=auth_headers(token),
    )
    assert resp.status_code == 400
    assert "size limit" in resp.json()["detail"]


async def test_non_member_cannot_upload(client: AsyncClient):
    _, _, task_id = await _setup_task(client)
    outsider_token, _ = await register_and_login(client, "attachoutsider@example.com", "Outsider")

    resp = await client.post(
        f"/api/tasks/{task_id}/attachments",
        files={"file": ("notes.txt", b"hello", "text/plain")},
        headers=auth_headers(outsider_token),
    )
    assert resp.status_code == 403


async def test_download_returns_presigned_url(client: AsyncClient):
    token, _, task_id = await _setup_task(client)
    upload = await client.post(
        f"/api/tasks/{task_id}/attachments",
        files={"file": ("notes.txt", b"hello world", "text/plain")},
        headers=auth_headers(token),
    )
    attachment_id = upload.json()["id"]

    resp = await client.get(
        f"/api/tasks/{task_id}/attachments/{attachment_id}/download", headers=auth_headers(token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["download_url"].startswith("http")
    assert "notes.txt" in body["download_url"] or body["expires_in"] == 300


async def test_delete_requires_admin(client: AsyncClient):
    owner_token, project_id, task_id = await _setup_task(client)
    member_token, _ = await register_and_login(client, "attachmember@example.com", "Member")
    await client.post(
        f"/api/projects/{project_id}/members",
        json={"email": "attachmember@example.com", "role": "member"},
        headers=auth_headers(owner_token),
    )
    upload = await client.post(
        f"/api/tasks/{task_id}/attachments",
        files={"file": ("notes.txt", b"hello", "text/plain")},
        headers=auth_headers(owner_token),
    )
    attachment_id = upload.json()["id"]

    forbidden = await client.delete(
        f"/api/tasks/{task_id}/attachments/{attachment_id}", headers=auth_headers(member_token)
    )
    assert forbidden.status_code == 403

    allowed = await client.delete(
        f"/api/tasks/{task_id}/attachments/{attachment_id}", headers=auth_headers(owner_token)
    )
    assert allowed.status_code == 204

    listed = await client.get(
        f"/api/tasks/{task_id}/attachments", headers=auth_headers(owner_token)
    )
    assert listed.json() == []


async def test_delete_attachment_removes_object_from_storage(client: AsyncClient, db_session):
    token, _, task_id = await _setup_task(client)
    upload = await client.post(
        f"/api/tasks/{task_id}/attachments",
        files={"file": ("notes.txt", b"hello", "text/plain")},
        headers=auth_headers(token),
    )
    attachment_id = upload.json()["id"]

    settings = get_settings()
    attachment = await attachment_crud.get_by_id(db_session, attachment_id)
    storage_key = attachment.storage_key

    s3 = get_s3_client()
    s3.head_object(Bucket=settings.s3_bucket, Key=storage_key)  # exists before delete

    delete_resp = await client.delete(
        f"/api/tasks/{task_id}/attachments/{attachment_id}", headers=auth_headers(token)
    )
    assert delete_resp.status_code == 204

    with pytest.raises(ClientError):
        s3.head_object(Bucket=settings.s3_bucket, Key=storage_key)


async def test_task_deletion_cleans_up_storage_object(client: AsyncClient, db_session):
    token, _, task_id = await _setup_task(client)
    upload = await client.post(
        f"/api/tasks/{task_id}/attachments",
        files={"file": ("notes.txt", b"hello", "text/plain")},
        headers=auth_headers(token),
    )
    attachment_id = upload.json()["id"]

    settings = get_settings()
    attachment = await attachment_crud.get_by_id(db_session, attachment_id)
    storage_key = attachment.storage_key

    s3 = get_s3_client()
    s3.head_object(Bucket=settings.s3_bucket, Key=storage_key)  # exists before delete

    delete_resp = await client.delete(f"/api/tasks/{task_id}", headers=auth_headers(token))
    assert delete_resp.status_code == 204

    with pytest.raises(ClientError):
        s3.head_object(Bucket=settings.s3_bucket, Key=storage_key)


async def test_activity_log_records_attachment_actions(client: AsyncClient):
    token, project_id, task_id = await _setup_task(client)
    upload = await client.post(
        f"/api/tasks/{task_id}/attachments",
        files={"file": ("notes.txt", b"hello", "text/plain")},
        headers=auth_headers(token),
    )
    attachment_id = upload.json()["id"]
    await client.delete(
        f"/api/tasks/{task_id}/attachments/{attachment_id}", headers=auth_headers(token)
    )

    resp = await client.get(f"/api/projects/{project_id}/activity", headers=auth_headers(token))
    actions = [entry["action"] for entry in resp.json()["items"]]
    assert "attachment_added" in actions
    assert "attachment_removed" in actions
