import logging
import uuid
from collections import defaultdict

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class NotificationConnectionManager:
    """
    Same shape as ConnectionManager (app/ws/connection_manager.py), but keyed only
    by user_id — notifications aren't scoped to a project room, they follow the
    user wherever they're connected.
    """

    def __init__(self) -> None:
        self._connections: dict[uuid.UUID, set[WebSocket]] = defaultdict(set)

    def connect(self, user_id: uuid.UUID, websocket: WebSocket) -> None:
        self._connections[user_id].add(websocket)

    def disconnect(self, user_id: uuid.UUID, websocket: WebSocket) -> None:
        connections = self._connections.get(user_id)
        if connections is None:
            return
        connections.discard(websocket)
        if not connections:
            del self._connections[user_id]

    async def send_to_user(self, user_id: uuid.UUID, message: dict) -> None:
        sockets = self._connections.get(user_id)
        if not sockets:
            return

        # Snapshot before iterating — same live-mutation race as ConnectionManager.
        # See PROGRESS.md Phase 4 bug list for why this matters.
        dead: list[WebSocket] = []
        for websocket in list(sockets):
            try:
                await websocket.send_json(message)
            except Exception:
                logger.warning(
                    "Dropping dead notification socket for user %s", user_id, exc_info=True
                )
                dead.append(websocket)

        for websocket in dead:
            self.disconnect(user_id, websocket)


notification_manager = NotificationConnectionManager()
