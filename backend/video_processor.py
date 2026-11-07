import numpy as np

class VideoProcessor:
    def __init__(self, yolo_model=None, classifier=None, tracker_path=None, yolo_device=None):
        self.yolo_model = yolo_model
        self.classifier = classifier
        self.tracker_path = tracker_path
        self.yolo_device = yolo_device

    def process_chunk(
        self,
        video_arrays: dict[str, dict],
        window_id: int
    ):
        for camera_id, video_data in video_arrays.items():
            frames = video_data["frames"]
            timestamp_from = video_data["from_timestamp"]
            timestamp_to = video_data["to_timestamp"]

        # TODO
        return None
