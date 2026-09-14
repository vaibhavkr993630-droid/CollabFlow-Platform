import logging
import uuid
from collections import defaultdict

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Tracks WebSocket connections live on *this* process only. A user can hold more
    than one connection to the same project room (multiple browser tabs), so
    connections are a set per (project_id, user_id), not a single socket.

    This class never decides *what* to broadcast — it only fans a message out to
    local sockets. The decision of what happened lives in app/ws/events.py and is
    always routed through Redis first (see redis_listener.py), even for the
    instance that triggered the event, so there is exactly one code path for
    "deliver this event to connected clients" regardless of which instance
    triggered it.
    """

    def __init__(self) -> None:
        self._connections: dict[uuid.UUID, dict[uuid.UUID, set[WebSocket]]] = defaultdict(
            lambda: defaultdict(set)
        )

    def connect(self, project_id: uuid.UUID, user_id: uuid.UUID, websocket: WebSocket) -> None:
        self._connections[project_id][user_id].add(websocket)

    def disconnect(self, project_id: uuid.UUID, user_id: uuid.UUID, websocket: WebSocket) -> None:
        project_conns = self._connections.get(project_id)
        if project_conns is None:
            return
        user_conns = project_conns.get(user_id)
        if user_conns is None:
            return
        user_conns.discard(websocket)
        if not user_conns:
            del project_conns[user_id]
        if not project_conns:
            del self._connections[project_id]

    def online_user_ids(self, project_id: uuid.UUID) -> set[uuid.UUID]:
        """Locally-known online users for this process — used only as a connect-time
        fallback; the source of truth for presence is Redis (see app/ws/presence.py)."""
        return set(self._connections.get(project_id, {}).keys())

    async def send_to_project(self, project_id: uuid.UUID, message: dict) -> None:
        project_conns = self._connections.get(project_id)
        if not project_conns:
            return

        # Snapshot both levels before the loop: `await websocket.send_json` yields
        # control, and a concurrent disconnect() (a real client dropping mid-relay,
        # not a hypothetical) mutates these same dict/set objects — iterating the
        # live structures raises "Set changed size during iteration" or dict-mutated
        # RuntimeErrors under that race. dict.items() view assumes underneath.
        snapshot = [(user_id, list(sockets)) for user_id, sockets in project_conns.items()]

        dead: list[tuple[uuid.UUID, WebSocket]] = []
        for user_id, sockets in snapshot:
            for websocket in sockets:
                try:
                    await websocket.send_json(message)
                except Exception:
                    logger.warning("Dropping dead WebSocket for user %s", user_id, exc_info=True)
                    dead.append((user_id, websocket))

        for user_id, websocket in dead:
            self.disconnect(project_id, user_id, websocket)


# Process-wide singleton — every WebSocket route and the Redis listener share it,
# matching the `engine`/`get_redis_client` singleton pattern used elsewhere.
connection_manager = ConnectionManager()
