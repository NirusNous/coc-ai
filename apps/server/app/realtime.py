import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import WebSocket


class WorkflowEventManager:
    def __init__(self):
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._history: dict[str, list[dict]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def connect(self, workflow_id: str, websocket: WebSocket) -> None:
        await websocket.accept()

        async with self._lock:
            self._connections[workflow_id].add(websocket)
            history = list(self._history[workflow_id])

        for event in history:
            await websocket.send_json(event)

    async def disconnect(self, workflow_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections[workflow_id].discard(websocket)

    async def publish(
        self,
        workflow_id: str,
        event_type: str,
        payload: dict,
    ) -> None:
        event = {
            "id": uuid4().hex,
            "workflowId": workflow_id,
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }

        async with self._lock:
            self._history[workflow_id].append(event)

            # Keep memory bounded during local development.
            self._history[workflow_id] = self._history[workflow_id][-500:]

            connections = list(self._connections[workflow_id])

        stale_connections: list[WebSocket] = []

        for websocket in connections:
            try:
                await websocket.send_json(event)
            except Exception:
                stale_connections.append(websocket)

        if stale_connections:
            async with self._lock:
                for websocket in stale_connections:
                    self._connections[workflow_id].discard(websocket)


workflow_event_manager = WorkflowEventManager()