from fastapi.testclient import TestClient


def _register_and_login(client: TestClient, email: str, name: str) -> tuple[str, str]:
    client.post(
        "/api/auth/register", json={"email": email, "password": "supersecret1", "full_name": name}
    )
    login = client.post("/api/auth/login", json={"email": email, "password": "supersecret1"})
    token = login.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    return token, me.json()["id"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _setup_project(client: TestClient) -> tuple[str, str]:
    token, _ = _register_and_login(client, "wsowner@example.com", "Owner")
    org = client.post("/api/organizations", json={"name": "WS Org"}, headers=_headers(token)).json()
    ws_resp = client.post(
        f"/api/organizations/{org['id']}/workspaces", json={"name": "Eng"}, headers=_headers(token)
    ).json()
    project = client.post(
        f"/api/workspaces/{ws_resp['id']}/projects",
        json={"name": "WS Project"},
        headers=_headers(token),
    ).json()
    return token, project["id"]


def test_websocket_connect_receives_presence_snapshot(ws_client: TestClient):
    token, project_id = _setup_project(ws_client)

    with ws_client.websocket_connect(f"/ws/projects/{project_id}?token={token}") as ws:
        snapshot = ws.receive_json()
        assert snapshot["type"] == "presence_snapshot"
        assert "online_user_ids" in snapshot["data"]


def test_websocket_rejects_invalid_token(ws_client: TestClient):
    _, project_id = _setup_project(ws_client)

    from starlette.websockets import WebSocketDisconnect

    try:
        with ws_client.websocket_connect(f"/ws/projects/{project_id}?token=garbage"):
            raise AssertionError("connection should have been rejected")
    except WebSocketDisconnect:
        pass


def test_websocket_rejects_non_member(ws_client: TestClient):
    _, project_id = _setup_project(ws_client)
    outsider_token, _ = _register_and_login(ws_client, "wsoutsider@example.com", "Outsider")

    from starlette.websockets import WebSocketDisconnect

    try:
        with ws_client.websocket_connect(f"/ws/projects/{project_id}?token={outsider_token}"):
            raise AssertionError("connection should have been rejected")
    except WebSocketDisconnect:
        pass


def test_websocket_receives_task_created_broadcast(ws_client: TestClient):
    token, project_id = _setup_project(ws_client)

    with ws_client.websocket_connect(f"/ws/projects/{project_id}?token={token}") as ws:
        ws.receive_json()  # presence_snapshot
        ws.receive_json()  # own presence_joined

        ws_client.post(
            f"/api/projects/{project_id}/tasks",
            json={"title": "Broadcast me"},
            headers=_headers(token),
        )

        event = ws.receive_json()
        assert event["type"] == "task_created"
        assert event["data"]["title"] == "Broadcast me"


def test_websocket_receives_comment_created_broadcast(ws_client: TestClient):
    token, project_id = _setup_project(ws_client)
    task = ws_client.post(
        f"/api/projects/{project_id}/tasks", json={"title": "Task"}, headers=_headers(token)
    ).json()

    with ws_client.websocket_connect(f"/ws/projects/{project_id}?token={token}") as ws:
        ws.receive_json()  # presence_snapshot
        ws.receive_json()  # own presence_joined

        ws_client.post(
            f"/api/tasks/{task['id']}/comments",
            json={"body": "hello"},
            headers=_headers(token),
        )

        event = ws.receive_json()
        assert event["type"] == "comment_created"
        assert event["data"]["body"] == "hello"


def test_presence_endpoint_reflects_connected_user(ws_client: TestClient):
    token, project_id = _setup_project(ws_client)
    user_id = ws_client.get("/api/auth/me", headers=_headers(token)).json()["id"]

    before = ws_client.get(f"/api/projects/{project_id}/presence", headers=_headers(token)).json()
    assert before["online_user_ids"] == []

    with ws_client.websocket_connect(f"/ws/projects/{project_id}?token={token}") as ws:
        ws.receive_json()  # presence_snapshot
        ws.receive_json()  # own presence_joined

        during = ws_client.get(
            f"/api/projects/{project_id}/presence", headers=_headers(token)
        ).json()
        assert during["online_user_ids"] == [user_id]

    # Disconnect-triggered presence cleanup (the server's `finally` block calling
    # presence.leave) is intentionally NOT asserted here: Starlette's TestClient
    # doesn't reliably deliver a WebSocket disconnect into a route's blocking
    # `receive_text()` loop in this environment — observed as the socket's
    # server-side task simply never waking back up after the client-side context
    # manager exits, even after several seconds of polling. This is a test-harness
    # limitation, not an app bug: verified against a real running `uvicorn` process
    # with the standalone `websockets` client (see PROGRESS.md) that presence.leave
    # and the resulting PRESENCE_LEFT broadcast fire correctly and promptly on an
    # actual disconnect.
