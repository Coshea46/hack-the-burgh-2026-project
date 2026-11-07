import time
import boto3
import imageio
import numpy as np
import queue
import threading
from collections import deque

from websocket_manager import WebSocketManager
from video_processor import VideoProcessor


class S3VideoIngester:
    """Reads videos from S3 and simulates real-time video ingestion."""
    def __init__(
        self,
        clip_size_seconds: int,
        stride_seconds: int,
        bucket_name: str,
        video_keys: list,
        ws_manager: WebSocketManager,
        processor: VideoProcessor,
        target_fps: float = 27.95,  # Change to match the videos stored in S3. Currently no dynamic setting for this.
        max_workers: int = 1,
        max_pending_windows: int = 2
    ):
        self.clip_size_seconds = clip_size_seconds
        self.stride_seconds = stride_seconds
        self.bucket_name = bucket_name
        self.video_keys = video_keys
        self.ws_manager = ws_manager
        self.processor = processor
        self.target_fps = target_fps
        self.max_workers = max_workers
        self.max_pending_windows = max_pending_windows

        if clip_size_seconds <= 0 or stride_seconds <= 0 or target_fps <= 0 or max_workers <= 0 or max_pending_windows <= 0:
            raise ValueError("Must be positive.")
        if stride_seconds > clip_size_seconds:
            raise ValueError("Stride should not exceed clip size.")

        self.window_size = int(self.clip_size_seconds * self.target_fps)
        self.stride_size = int(self.stride_seconds * self.target_fps)
        self.s3_client = boto3.client("s3")

        self.frame_buffers = {key: deque(maxlen=self.window_size) for key in self.video_keys}
        self.frame_counts = {key: 0 for key in self.video_keys}

        self.processing_queue = queue.Queue(maxsize=self.max_pending_windows)

        # Worker management.
        self.workers = []
        self.stop_event = threading.Event()

        # Prevent older processing results from overwriting newer ones.
        self.result_lock = threading.Lock()
        self.last_broadcast_window_id = -1

    def generate_urls(self):
        """Generate presigned URLs for all S3 video objects."""
        return [
            self.s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": key},
                ExpiresIn=6000
            )
            for key in self.video_keys
        ]

    def _open_readers(self, urls):
        """Open imageio readers for all video streams."""
        readers = {}

        for key, url in zip(self.video_keys, urls):
            reader = imageio.get_reader(url, "ffmpeg")
            metadata = reader.get_meta_data()
            source_fps = metadata.get("fps")

            if source_fps is None or source_fps <= 0:
                reader.close()
                raise ValueError(f"Could not determine FPS for {key}.")

            if abs(source_fps - self.target_fps) > 0.01:
                reader.close()
                raise ValueError(f"{key} has FPS {source_fps}, but target_fps is {self.target_fps}. ")

            readers[key] = reader

        return readers

    def _read_next_frames(self, readers, active_cameras):
        """Read one frame from every active camera. Frames are converted from RGB to BGR."""
        received_frame = False

        for camera_key, reader in readers.items():
            if not active_cameras[camera_key]:
                continue

            try:
                frame = reader.get_next_data()
                frame = frame[:, :, ::-1].copy()
                self.frame_buffers[camera_key].append(frame)
                self.frame_counts[camera_key] += 1
                received_frame = True
            except IndexError:
                print(f"[S3VideoIngester] End of stream: {camera_key}", flush=True)
                active_cameras[camera_key] = False

        return received_frame

    def _generate_video_arrays(self):
        """Snapshot the rolling buffers into NumPy arrays."""
        video_arrays = {}

        for camera_key, buffer in self.frame_buffers.items():
            if len(buffer) < self.window_size:
                continue
            frame_count = self.frame_counts[camera_key]
            video_arrays[camera_key] = {
                "frames": np.stack(list(buffer)),
                "from_timestamp": frame_count / self.target_fps,
                "to_timestamp": (frame_count - self.window_size) / self.target_fps
            }
        return video_arrays

    def _start_workers(self):
        """Start the configured number of processing workers."""
        self.stop_event.clear()

        for worker_id in range(self.max_workers):
            worker = threading.Thread(
                target=self._worker_loop,
                args=(worker_id,),
                name=f"VideoProcessor-{worker_id}",
                daemon=True
            )
            worker.start()
            self.workers.append(worker)

        print(f"[S3VideoIngester] Started {self.max_workers} workers.", flush=True)

    def _stop_workers(self):
        self.stop_event.set()
        for worker in self.workers:
            worker.join()
        self.workers.clear()
        print("[S3VideoIngester] All workers stopped.", flush=True)

    def _dispatch_window(self, video_arrays, window_id):
        """Add a completed window to the processing queue."""
        job = {"window_id": window_id, "video_arrays": video_arrays}

        try:
            self.processing_queue.put_nowait(job)
        except queue.Full:
            try:
                self.processing_queue.get_nowait()
                self.processing_queue.task_done()
                print(f"[S3VideoIngester] Dropping stale window to prioritise window {window_id}.", flush=True)
            except queue.Empty:
                pass
            # Add the latest window.
            self.processing_queue.put_nowait(job)

    def _worker_loop(self, worker_id):
        while not self.stop_event.is_set() or not self.processing_queue.empty():
            try:
                job = self.processing_queue.get(timeout=0.25)
            except queue.Empty:
                continue

            try:
                window_id = job["window_id"]
                video_arrays = job["video_arrays"]

                print(f"[Worker {worker_id}] Processing window {window_id}.", flush=True)
                best_feed = self.processor.process_chunk(video_arrays, window_id)

                # TODO: REMOVE THIS. WE DISPATCH HERE BECAUSE THE BROADCAST BELOW WOULD NEVER BE REACHED OTHERWISE.
                self.ws_manager.broadcast({
                    "type": "switch",
                    "target_feed": "cam-1",
                    "from_timestamp": "0",
                    "to_timestamp": "5",
                    "window_id": 1
                })

                # Broadcast only if this result is newer than the last successfully broadcast result.
                with self.result_lock:
                    if best_feed is not None and window_id > self.last_broadcast_window_id:
                        self.ws_manager.broadcast({
                            "type": "switch",
                            "target_feed": best_feed["camera_id"],
                            "from_timestamp": best_feed["from_timestamp"],
                            "to_timestamp": best_feed["to_timestamp"],
                            "window_id": window_id
                        })
                        self.last_broadcast_window_id = window_id

            except Exception as e:
                print(f"[Worker {worker_id}] Processing error: {e}", flush=True)
            finally:
                self.processing_queue.task_done()

    def run_loop(self):
        """Main real-time ingestion loop (which mimics real-time streaming)."""
        print("[S3VideoIngester] Generating S3 URLs...", flush=True)
        readers = self._open_readers(self.generate_urls())
        active_cameras = {key: True for key in self.video_keys}
        self._start_workers()

        print(
            f"[S3VideoIngester] Starting ingestion.\n"
            f"Clip size: {self.clip_size_seconds}s\n"
            f"Stride: {self.stride_seconds}s\n"
            f"Target FPS: {self.target_fps}\n"
            f"Window frames: {self.window_size}\n"
            f"Stride frames: {self.stride_size}",
            flush=True
        )

        frame_index = 0
        window_id = 0
        start_time = time.monotonic()
        try:
            while any(active_cameras.values()):
                # The next frame becomes available at this time.
                next_frame_time = start_time + frame_index / self.target_fps

                # Wait only if decoding is ahead of playback time.
                wait_time = next_frame_time - time.monotonic()

                if wait_time > 0:
                    time.sleep(wait_time)

                # Read one frame from every active camera.
                received_frame = self._read_next_frames(readers, active_cameras)
                if not received_frame:
                    break

                frame_index += 1
                # Wait until a complete initial window exists.
                if frame_index < self.window_size:
                    continue

                # Dispatch only at the configured stride.
                if (frame_index - self.window_size) % self.stride_size != 0:
                    continue

                # Snapshot the current windows.
                video_arrays = self._generate_video_arrays()
                if not video_arrays:
                    continue

                print(f"[S3VideoIngester] Dispatching window {window_id}.", flush=True)
                self._dispatch_window(video_arrays, window_id)
                window_id += 1

        except KeyboardInterrupt:
            print("[S3VideoIngester] Interrupted.", flush=True)
        finally:
            for reader in readers.values():
                reader.close()
            # Finish outstanding processing jobs.
            self._stop_workers()
            print("[S3VideoIngester] Ingestion terminated.", flush=True)
