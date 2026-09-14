import uuid

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from redis.asyncio import Redis

from app.core.deps import require_ws_project_role
from app.core.redis import get_redis_client
from app.models.roles import Role
from app.models.user import User
from app.ws import presence
from app.ws.connection_manager import connection_manager
from app.ws.events import WSEventType, publish_event

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/projects/{project_id}")
async def project_websocket(
    websocket: WebSocket,
    project_id: uuid.UUID,
    user: User = Depends(require_ws_project_role(Role.MEMBER)),
    redis: Redis = Depends(get_redis_client),
) -> None:
    await websocket.accept()
    connection_manager.connect(project_id, user.id, websocket)

    # Snapshot must reach this socket before the PRESENCE_JOINED broadcast does, or
    # the client sees its own join event before it has any idea who else is online.
    # Sending it first (and fully awaiting that send) before publishing anything to
    # Redis guarantees the ordering: the listener task can't relay PRESENCE_JOINED
    # to this same socket until *after* our own send_json call below has returned.
    connection_count = await presence.join(redis, project_id=project_id, user_id=user.id)
    online_ids = await presence.online_user_ids(redis, project_id=project_id)
    await websocket.send_json(
        {
            "type": WSEventType.PRESENCE_SNAPSHOT.value,
            "project_id": str(project_id),
            "actor_id": None,
            "data": {"online_user_ids": online_ids},
        }
    )

    if connection_count == 1:
        await publish_event(
            redis,
            project_id=project_id,
            event_type=WSEventType.PRESENCE_JOINED,
            data={"user_id": str(user.id)},
            actor_id=user.id,
        )

    try:
        while True:
            # Clients don't send anything meaningful yet (no chat/typing-indicator
            # feature in scope) — this just keeps the connection open and lets
            # FastAPI raise WebSocketDisconnect when the client goes away.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        connection_manager.disconnect(project_id, user.id, websocket)
        remaining = await presence.leave(redis, project_id=project_id, user_id=user.id)
        if remaining <= 0:
            await publish_event(
                redis,
                project_id=project_id,
                event_type=WSEventType.PRESENCE_LEFT,
                data={"user_id": str(user.id)},
                actor_id=user.id,
            )
