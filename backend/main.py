import asyncio
import websockets
import threading
import os
import boto3
import numpy as np

from websocket_manager import WebSocketManager
from video_ingester import S3VideoIngester
from video_processor import VideoProcessor

CLIP_SIZE_SECONDS = 5
STRIDE_SECONDS = 4
VIDEO_KEYS = ["matches/230024607-Video_presentation.mp4"]


class AppController:
    """The central orchestrator."""

    def __init__(self):
        self.bucket_name = os.environ.get("S3_BUCKET_NAME")
        if not self.bucket_name:
            raise ValueError("ERROR: S3_BUCKET_NAME environment variable not set.")

        self.ws_manager = WebSocketManager()
        self.processor = VideoProcessor()
        self.ingester = S3VideoIngester(
            CLIP_SIZE_SECONDS, STRIDE_SECONDS, self.bucket_name, VIDEO_KEYS, self.ws_manager, self.processor
        )

    async def start(self):
        # Start the video ingestion loop in a background daemon thread.
        ingestion_thread = threading.Thread(target=self.ingester.run_loop, daemon=True)
        ingestion_thread.start()

        await self.ws_manager.serve()


if __name__ == "__main__":
    app = AppController()
    try:
        asyncio.run(app.start())
    except KeyboardInterrupt:
        print("\nServer shutting down.", flush=True)
