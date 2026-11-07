import asyncio
import websockets
import json
import cv2
import boto3
import numpy as np

class WebSocketManager:
    """Manages WebSocket connections and broadcasts to connected frontend clients."""

    def __init__(self, host="0.0.0.0", port=8000):
        self.host = host
        self.port = port
        self.clients = set()
        self.loop = None

    async def handler(self, websocket):
        self.clients.add(websocket)
        client_address = websocket.remote_address
        print(f"[WebSocket] Client connected from {client_address}. Total clients: {len(self.clients)}")

        try:
            # Sync with the new client.
            # TODO send the most up to date timestamp.
            sync_payload = json.dumps({"type": "sync", "current_live_timestamp": 0.0})
            await websocket.send(sync_payload)
            await websocket.wait_closed()
        finally:
            self.clients.remove(websocket)
            print(f"[WebSocket] Client disconnected. Total clients: {len(self.clients)}")

    def broadcast(self, payload: dict):
        if not self.clients or not self.loop:
            return

        # Broadcast to all connected clients.
        self.loop.call_soon_threadsafe(
            websockets.broadcast, self.clients, json.dumps(payload)
        )
        print(f"[WebSocket] Broadcasted: {payload}")

    async def serve(self):
        """Starts the WebSocket server."""
        self.loop = asyncio.get_running_loop()
        print(f"WebSocket server listening on ws://{self.host}:{self.port}")
        async with websockets.serve(self.handler, self.host, self.port):
            await asyncio.Future()
