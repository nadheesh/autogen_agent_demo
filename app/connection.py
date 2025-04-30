from typing import Dict

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        # Stores active WebSocket connections mapped by session ID
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, session_id: str, websocket: WebSocket):
        """
        Accept a new WebSocket connection and add it to the active connections.
        """
        await websocket.accept()
        self.active_connections[session_id] = websocket

    def disconnect(self, session_id: str):
        """
        Remove a WebSocket connection from the active connections by session ID.
        """
        self.active_connections.pop(session_id, None)

    async def send_message(self, session_id: str, message: str):
        """
        Send a JSON-formatted message to the WebSocket associated with the given session ID.
        """
        websocket = self.active_connections.get(session_id)
        if websocket:
            await websocket.send_json(message)

    async def receive_message(self, session_id: str):
        """
        Wait to receive a text message from the WebSocket associated with the given session ID.
        Returns None if the session is not connected.
        """
        websocket = self.active_connections.get(session_id)
        if websocket:
            return await websocket.receive_text()
        return None

    async def broadcast(self, message: str):
        """
        Send a text message to all active WebSocket connections.
        """
        for websocket in self.active_connections.values():
            await websocket.send_text(message)
