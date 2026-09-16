# Phase 6 — Files

> Tasks can now carry file attachments, stored in an S3-compatible bucket rather than on the
> app server's own disk. This is also the last backend feature phase per the original brief —
> Phases 7-9 are frontend, hardening, and deployment.

## Scope

| In | Out (later phases) |
|---|---|
| `Attachment` model + migration | Frontend upload UI (Phase 7) |
| boto3/MinIO storage wrapper | Content-type restrictions (explicitly deferred) |
| Upload/list/download/delete endpoints | Configurable presigned-URL expiry (explicitly deferred) |
| Task-deletion storage cleanup | — |

## Why presigned URLs, not a proxied download

```
GET /api/tasks/{id}/attachments/{id}/download
        │
        ▼
  { "download_url": "http://minio:9000/...&X-Amz-Signature=...", "expires_in": 300 }
        │
        ▼
  client fetches the file bytes DIRECTLY from MinIO — the API server never touches them
```

The API server generates a time-limited, signed URL and hands it back; the client then talks to
MinIO directly. The alternative — the API server reading the object and streaming it back through
itself — would work, but means every download's bandwidth and memory pressure lands on the API
process for no benefit. Presigned URLs default to 5 minutes, long enough for a client to start a
download promptly, short enough that a leaked URL isn't a standing liability.

## `build_storage_key`: a small security decision, explained

```python
def build_storage_key(task_id: uuid.UUID, filename: str) -> str:
    safe_filename = filename.replace("\\", "/").rsplit("/", 1)[-1]
    return f"tasks/{task_id}/{uuid.uuid4().hex}_{safe_filename}"
```

Two things happen here, both deliberate:

1. **Path components are stripped from the client-supplied filename.** A filename of
   `"../../etc/passwd"` or `"a/b/c"` would otherwise become part of the object key verbatim —
   MinIO's key namespace is flat but slash-delimited prefixes act like directories in its UI and
   in any tooling that assumes a filesystem shape. An attacker-controlled filename shouldn't be
   able to nest into, or escape, the intended `tasks/{task_id}/` prefix.
2. **A fresh UUID prefixes every key**, not just `task_id` + filename. Two uploads of
   `report.pdf` to the same task must not silently overwrite each other in the bucket — the
   `Attachment.storage_key` column (unique, stored explicitly) is what the app actually reads
   back; the filename in the key is for human-readability when browsing the bucket directly, not
   for lookup.

## `ON DELETE CASCADE`, a deliberate contrast with Phase 3/5's `SET NULL`

```python
task_id: Mapped[uuid.UUID] = mapped_column(
    PGUUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
)
```

`ActivityLog.task_id` and `Notification.task_id` are both `SET NULL` — they're *records about*
something, and a record should outlive the thing it describes. An `Attachment` is not a record
about a file, **it is the file's metadata pointer** — there's no meaningful state for "an
attachment whose task no longer exists." Deleting a task should take its attachments with it, not
orphan them. This is the same modeling question (what survives a delete?) reaching a different,
equally deliberate answer because the entity's relationship to its parent is different in kind.

Deleting a task's Postgres row cascades to its `attachments` rows automatically — but MinIO has no
idea a foreign key exists. `task_service.delete_task` fetches every attachment's `storage_key`
and calls `delete_object` on each **before** the task row (and its cascading attachment rows) are
actually deleted, because the keys need to still be readable from the database at that point to
know what to delete from the bucket.

## Asymmetric ordering: upload vs. delete

**Upload** — storage write before DB row:

```python
upload_bytes(key=storage_key, data=data, content_type=content_type)   # 1: MinIO
attachment = await attachment_crud.create(db, ...)                     # 2: DB row
await db.commit()
```

If the MinIO write fails, nothing needs rolling back — no database row was ever written pointing
at a file that doesn't exist.

**Delete** — DB row before storage delete:

```python
await attachment_crud.delete(db, attachment)   # 1: DB row
await db.commit()
delete_object(key=storage_key)                  # 2: MinIO, after commit
```

The metadata row is what a user perceives as "the attachment is gone." If MinIO happens to be
briefly unreachable at that exact moment, the delete request still succeeds rather than failing
on an infrastructure hiccup — at the cost of a possible orphaned object left in the bucket if step
2 never runs. That's a stated tradeoff, not an oversight: worth revisiting with a cleanup job or
outbox pattern if orphaned objects ever become a real operational problem at scale, not needed at
this project's size.

## A real bug: boto3 hanging, not erroring

The first attempt at every S3 call — `ensure_bucket_exists()`, an upload, anything — hung for
30+ seconds and then failed with no useful error message. This surfaced as a full pytest run
timing out with nothing actionable in the output.

**Diagnosis:** rather than guess, the investigation isolated the problem down to a plain
three-line script (`boto3.client("s3", endpoint_url=...).list_buckets()`) run completely outside
pytest and the app. It hung identically. Meanwhile, `curl` directly against MinIO's own health
endpoint succeeded immediately and consistently — which pointed at boto3's *client construction*,
not MinIO itself, as the actual problem.

**Root cause:** no `region_name` was passed to `boto3.client()`. Without one, boto3 attempts to
resolve a region via the EC2 instance metadata service at `169.254.169.254` before falling back
to anything else — and that lookup *hangs* rather than failing fast in any environment that isn't
an actual EC2 instance, which is every environment this project runs in (local dev, CI, this
session's own sandbox).

**Fix:** an explicit `region_name="us-east-1"` — the value is meaningless to MinIO, which ignores
it entirely, but its mere presence skips the metadata-service lookup altogether.

**The generalizable lesson:** boto3 configured against a non-AWS S3-compatible endpoint (MinIO,
R2, B2, etc.) needs an explicit region even though that endpoint has no concept of AWS regions —
and when boto3 hangs rather than raises a clean error, region auto-detection is the first thing
to suspect, not the target service.

## Known simplifications, stated rather than hidden

- **No content-type restriction on uploads** beyond the size cap — any file type is accepted.
  MinIO never executes stored objects, so this isn't a code-execution surface the way serving
  uploads back through the app server's own process would be. The actual gap is UX (not blocking
  an obviously-wrong `.exe` at the API layer), not security.
- **Presigned URL expiry is a fixed 5 minutes**, not configurable per request or per attachment
  sensitivity. Sufficient for this project's scope.

## Files added or changed

```
backend/app/
  core/storage.py                  # NEW — boto3 singleton, bucket provisioning, key building
  core/config.py                   # s3_endpoint_url/access_key/secret_key/bucket, max size
  models/attachment.py             # NEW — Attachment (task_id ON DELETE CASCADE)
  models/activity.py                # ATTACHMENT_ADDED / ATTACHMENT_REMOVED
  ws/events.py                      # ATTACHMENT_ADDED / ATTACHMENT_REMOVED WSEventType
  crud/attachment.py                # NEW
  schemas/attachment.py             # NEW — AttachmentRead, AttachmentDownloadRead
  services/attachment_service.py    # NEW — upload_attachment, delete_attachment
  services/task_service.py          # storage cleanup on task deletion
  api/routers/attachments.py        # NEW — upload/list/download/delete
  main.py                           # ensure_bucket_exists() in lifespan
backend/migrations/versions/f17665be6383_phase6_attachments.py
backend/tests/test_attachments.py
```

## How to verify

```bash
docker compose up -d postgres redis minio
cd backend
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head        # now at f17665be6383
uvicorn app.main:app --reload &
pytest
```

MinIO's own console is at `http://localhost:9001` (login: `S3_ACCESS_KEY`/`S3_SECRET_KEY` from
`.env`) to browse the bucket directly.

## What Phase 7 builds on this

Backend feature work per the original brief's phase list is complete as of this phase — Phase 7
is where a real frontend finally consumes everything Phases 1-6 built: auth, projects/tasks,
real-time updates, notifications, and now file attachments, all from one React app.
