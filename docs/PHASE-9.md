# Phase 9 — Closing the frontend gaps

**Goal:** make the UI show what the backend can actually do. Phases 1–6 built a capable API;
Phase 7 built a board on top of a slice of it. This phase closes the distance between the two,
because the live demo is the only part of this project most people will ever open.

---

## The gap, measured

Before starting, every `frontend/src/api/*.ts` helper was checked against the screens that call
it. Seven helpers existed that **no screen used at all**:

| Helper | Backend feature it exposed |
|---|---|
| `inviteWorkspaceMember`, `listWorkspaceMembers` | workspace membership + roles |
| `inviteProjectMember`, `listProjectMembers` | project membership + roles |
| `createLabel` | creating labels (only toggling existing ones was wired) |
| `listSubtasks` | subtasks |
| `listProjectActivity` | the project-wide activity feed |

The practical effect: **two people could not be connected through the UI at all.** There was no
way to invite anyone, roles were invisible, and a task could not be assigned to a person — which
also meant the `task_assigned` notification was unreachable in practice. The board showed the
project's tasks but never its name.

---

## Delivered

### Membership and roles

- **`MembersPanel`** (`frontend/src/components/MembersPanel.tsx`) — one component used for both
  workspaces and projects. Lists members with an avatar, name, email and a role badge, and gives
  owners/admins an "add by email" form with a role picker.
- Shown on the dashboard for the selected workspace, and behind a **Members** dialog on the board.
- The invite form is hidden for plain members, matching the 403 the backend already returns — the
  rule is enforced server-side; the UI just stops offering an action that would fail.
- Error text is the backend's own where it is useful: inviting someone with no account shows
  **"No user found with that email"** rather than a generic failure.

**Backend change this required:** membership responses carried only a `user_id`, so no UI could
show *who* a member was without N extra requests. `ProjectMemberRead` / `WorkspaceMemberRead` now
embed a small `UserBrief` (`id`, `email`, `full_name`). The list queries eager-load the user with
`selectinload`, and the invite path attaches the already-loaded user with `set_committed_value` —
async SQLAlchemy raises on a lazy load, so the relationship has to be populated deliberately.

### Assignees

- Assignee dropdown in the task panel, populated from the project's members.
- Assignee initials on the board card, coloured by a hash of the name so one person keeps the same
  colour everywhere (`Avatar`).
- This is what makes the "task assigned" notification reachable from the UI for the first time.

### Subtasks, labels, activity

- **Subtasks** — create and tick off child tasks in the task panel, with an `n/m done` counter.
  Ticking one is optimistic, with rollback on failure, matching the board's drag-and-drop.
- **Create labels** — a name + colour-picker form in the task panel. The Labels section was
  previously unusable on a new project, because nothing could create the first label.
- **Project activity feed** — a slide-over drawer, paginated with `useInfiniteQuery`. Actor ids
  are resolved to names, and the backend's raw field names are humanised for display
  (`(assignee_id, label_ids)` → `(assignee, labels)`).

### Search, filter, sort

The board now drives the query parameters that Phase 3 built and nothing had used: title search,
priority, assignee, label, and five sort options. Filters are part of the React Query cache key,
so each combination caches separately, while every live-update handler invalidates by the
`['tasks', projectId]` prefix and so refreshes all of them.

### Getting the project's own name

Ironically the board could not show the project it was displaying: there was no endpoint to fetch
one project. Added **`GET /api/projects/{id}`**, guarded by the existing project-membership
dependency.

This exposed a real distinction worth surfacing rather than hiding: **workspace membership and
project membership are independent** (`require_project_role`'s docstring has always said so). A
workspace member who opens a project they are not in gets a 403. Rather than a blank failure, the
board now explains it: *"Being in the workspace lets you see the project exists. To open its
board, an owner or admin of the project needs to add you to it."*

### Polish

- Page title was literally `frontend`; now a real title, description and a CollabFlow favicon
  replacing Vite's default.
- Empty states everywhere they were missing ("No organizations yet…", "No tasks yet. Quick-add one
  above…", "Drop a task here", "No comments yet").
- Failed mutations render a readable sentence via a shared `errorMessage` helper that understands
  FastAPI's two `detail` shapes (a string for app errors, a list for 422 validation errors) and
  the no-response case ("Can't reach the server").
- Checked at 390px wide: no horizontal overflow, columns stack, the task panel is usable.

### Email that actually works

Reset and notification mail went out as `MIMEText` plain text, which is **why the reset link was
not clickable** in most mail clients. Mail is now `multipart/alternative`: a table-based HTML
version with a real button, plus the same content as plain text with the URL on its own line.

Everything interpolated into the HTML goes through `html.escape` — task titles, project names and
people's names are user-controlled text, and an unescaped `<` in an email is an injection bug
rather than a display glitch. There is a test that registers a user called `Mail <b>Test</b>` and
asserts the markup arrives escaped.

### Local-stack hardening

`docker-compose.yml` published Postgres, Redis, MinIO and MailDev on **every** interface, so
anything that could reach the machine could reach a database with development-default
credentials. All four now bind to `127.0.0.1`.

---

## Deployment configuration (ported, not yet applied)

The hosted setup from the original build is now in this repository as clean commits:

- **`.railway/railway.ts`** — Postgres, Redis, MinIO, the API and a combined worker+beat service
  as infrastructure-as-code. No secret literals: real values are set with `railway variable set`
  and declared here with `preserve()` so a later `config apply` does not treat them as drift.
- **`frontend/vercel.json`** — SPA rewrite, so refreshing on `/projects/:id` does not 404.
- **`frontend/src/ws/wsBaseUrl.ts`** — in production the frontend (Vercel) and backend (Railway)
  are on different domains with no proxy, so the WebSocket URL must come from `VITE_API_BASE_URL`.
  Using `window.location.host` there silently opens a socket against the static host, which has no
  `/ws` route — this was live-broken in production until a real browser test on the deployed site
  caught it.
- **SMTP auth** — `smtp_user` / `smtp_password` switch `send_email` into STARTTLS + login, so the
  same function serves MailDev locally and a real relay in production.

Two fixes were needed while porting: the IaC file still referenced the Docker Hub `minio/minio`
image (no longer served — now the pinned Quay image) and the **deleted** `collabflow` repository
as its build source.

`FRONTEND_URL` was also missing from the production environment entirely. Left unset it defaults
to `http://localhost:5173`, which would have made **every password-reset email sent from
production a dead link**.

---

## Verification

Backend: `ruff check` clean, full suite green (`pytest`), including new tests for the embedded
user in membership responses, the `GET /api/projects/{id}` permission rule, HTML/plain multipart
structure, and HTML escaping.

Frontend: `tsc -b` and `vite build` clean; `oxlint` reports no new warnings.

End-to-end, in a real headless browser against the real Docker stack (Postgres, Redis, MinIO,
MailDev), with three accounts:

- workspace and project invites, including the "no user with that email" error path
- role badges, and a plain member correctly seeing no invite form
- assignee selection reaching the card as an avatar
- label creation, subtask create + complete, comments showing real author names
- search, assignee and label filters each narrowing the board
- the activity feed listing the invite and task events
- **two browsers open on the same board**: a task created by one appeared in the other with no
  refresh (the WebSocket path)
- a third account, in neither project nor workspace, getting the explanatory page rather than a
  raw 403
- the reset email opened and rendered: branded button, working link, escaped name

---

## Known limitations (deliberate, not oversights)

These need new backend endpoints that do not exist yet, and are called out honestly rather than
faked in the UI:

- No renaming or deleting an organization, workspace or project.
- No changing a member's role or removing a member after they are added.
- No editing or deleting a comment.
- Invites require the invitee to **already have an account** — there are no invite links or email
  verification.
- A password reset does not revoke existing sessions, and `forgot-password` is not rate-limited.
