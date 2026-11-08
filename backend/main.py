"""Application backend: source registration, replay clock, director and WebSocket."""

import asyncio
import logging
import os

if __package__:
    from .replay import ReplaySession, SessionConfig, SourceRegistry
    from .websocket_manager import WebSocketManager
else:  # ``python main.py`` in the backend Docker image
    from replay import ReplaySession, SessionConfig, SourceRegistry
    from websocket_manager import WebSocketManager


class AppController:
    def __init__(self, *, registry=None, config=None, bridge=None, host=None, port=None):
        self.session = ReplaySession(registry or SourceRegistry.from_env(),
                                     config=config or SessionConfig.from_env(), bridge=bridge)
        self.ws_manager = WebSocketManager(self.session,
                                           host=host or os.environ.get("MATCHPULSE_HOST", "0.0.0.0"),
                                           port=int(os.environ.get("MATCHPULSE_PORT", "8000")) if port is None else port)

    async def start(self):
        await self.session.initialize()
        self.session.start()
        try:
            await self.ws_manager.serve()
        finally:
            await self.session.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    # SDK debug logs can contain signed URLs. Application errors report classes,
    # never media payloads or source credentials.
    for name in ("boto3", "botocore", "urllib3", "websockets"):
        logging.getLogger(name).setLevel(logging.WARNING)
    try:
        asyncio.run(AppController().start())
    except KeyboardInterrupt:
        pass
