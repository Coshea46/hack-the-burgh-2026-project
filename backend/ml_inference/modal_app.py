"""Independent inference deployment. Import via Modal CLI only, after approval.

No references to matchpulse-private or its Volumes/leases/controllers are used.
The ordinary public package does not import this module.
"""

import os
from pathlib import Path
from time import perf_counter

import modal

from backend.ml_inference.config import APP_NAME, MODEL_VOLUME

PACKAGE = Path(__file__).resolve().parent
GPU = os.environ.get("MATCHPULSE_ML_GPU", "T4")
CONTAINERS = int(os.environ.get("MATCHPULSE_ML_WORKER_CONCURRENCY", "1"))
TIMEOUT = int(os.environ.get("MATCHPULSE_ML_WORKER_TIMEOUT_SECONDS", "180"))
SCALEDOWN = int(os.environ.get("MATCHPULSE_ML_SCALEDOWN_SECONDS", "5"))
CLASSIFIER_TIMEOUT = int(os.environ.get("MATCHPULSE_ML_CLASSIFIER_TIMEOUT_SECONDS", "60"))
if min(CONTAINERS, TIMEOUT, SCALEDOWN, CLASSIFIER_TIMEOUT) < 1:
    raise ValueError("Inference deployment resource values must be positive")

app = modal.App(APP_NAME)

if modal.is_local():
    from backend.ml_inference.packaging import runtime_artifacts

    wheel, weights = runtime_artifacts(os.environ.get("MATCHPULSE_ML_WEIGHTS"))
    image = (
        modal.Image.debian_slim(python_version="3.13")
        .apt_install("libgl1", "libglib2.0-0")
        .pip_install("torch==2.11.0", "torchvision==0.26.0",
                     index_url="https://download.pytorch.org/whl/cu130")
        .pip_install_from_requirements(str(PACKAGE / "requirements-worker.txt"))
        .add_local_file(str(wheel), "/opt/runtime/matchpulse-0.1.0-py3-none-any.whl", copy=True)
        .run_commands("python -m pip install --no-deps /opt/runtime/matchpulse-0.1.0-py3-none-any.whl")
        .add_local_file(str(weights), "/opt/models/yolo26s.pt", copy=True)
        .env({"PYTHONPATH": "/opt/client", "YOLO_CONFIG_DIR": "/tmp/matchpulse-inference-ultralytics"})
        .add_local_dir(str(PACKAGE), "/opt/client/backend/ml_inference",
                       ignore=["tests/**", "runtime/**", "artifacts/**", ".venv*/**",
                               "**/__pycache__/**", "**/*.pyc", ".pytest_cache/**"])
    )
else:
    image = modal.Image.debian_slim(python_version="3.13")

# New inference-only storage, resolved/created by a future authorized deployment.
models = modal.Volume.from_name(MODEL_VOLUME, create_if_missing=True)


def detector_runtime(detector, expected_fp16):
    # Ultralytics setup_model deep-copies the source model. Verify the active
    # prediction backend, whose parameters actually perform inference.
    predictor = detector.model.predictor
    backend = predictor.model
    parameter = next(backend.model.parameters())
    device, dtype = str(parameter.device), str(parameter.dtype)
    if not device.startswith("cuda") or not str(predictor.device).startswith("cuda"):
        raise RuntimeError("Active detector prediction backend did not execute on CUDA")
    if bool(backend.fp16) != expected_fp16 or dtype != ("torch.float16" if expected_fp16 else "torch.float32"):
        raise RuntimeError("Active detector prediction precision differs from configuration")
    return {"detector_device": device, "predictor_device": str(predictor.device),
            "detector_dtype": dtype, "detector_fp16": bool(backend.fp16)}


@app.cls(image=image, gpu=GPU, cpu=(1, 4), memory=(2048, 8192), max_containers=CONTAINERS,
         min_containers=0, buffer_containers=0, scaledown_window=SCALEDOWN,
         timeout=TIMEOUT, startup_timeout=300, retries=0, include_source=False)
class FeatureWorker:
    fp16: bool = modal.parameter(default=True)
    max_window_bytes: int = modal.parameter(default=512 * 1024 * 1024)

    @modal.enter()
    def load(self):
        started = perf_counter()
        import torch

        from backend.ml_inference.extraction import ResearchFeatureExtractor

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA feature extraction is required; no automatic CPU fallback")
        self.extractor = ResearchFeatureExtractor(
            "/opt/models/yolo26s.pt", device="cuda:0", fp16=self.fp16
        ).prepare()
        self.runtime = {
            "gpu": torch.cuda.get_device_name(0), "torch": str(torch.__version__),
            "cuda": torch.version.cuda, "fp16": self.fp16,
            "container_id": os.environ.get("MODAL_TASK_ID"),
        }
        self.initialization_seconds = perf_counter() - started
        self.calls = 0

    @modal.method()
    def extract(self, payload):
        from backend.ml_inference.transport import (
            AV_TRANSPORT_VERSION,
            decode_request,
            decode_window,
        )

        started = perf_counter()
        full_audio = isinstance(payload, dict) and payload.get("version") == AV_TRANSPORT_VERSION
        if full_audio:
            match_id, frames, audio = decode_request(payload, max_bytes=self.max_window_bytes)
        else:
            match_id, audio = "window", None  # Explicit legacy test transport only.
            frames = decode_window(payload, max_bytes=self.max_window_bytes)
        decode_seconds = perf_counter() - started
        # No modal.concurrent decorator: each container serializes inputs. The
        # research extractor resets tracking for each complete window.
        self.extractor.clear_cache()
        self.calls += 1
        t = perf_counter()
        features = self.extractor.extract(match_id, frames, audio) if full_audio else self.extractor.extract(match_id, frames)
        if not full_audio:
            return features
        extraction_seconds = perf_counter() - t
        return {"match_id": match_id, "features": features,
                "metrics": {"runtime": {**self.runtime, **detector_runtime(self.extractor._extractor.detector, self.fp16)},
                            "decode_seconds": decode_seconds, "extraction_seconds": extraction_seconds,
                            "initialization_seconds": self.initialization_seconds,
                            "detector_load_seconds": self.extractor._extractor.model_load_seconds,
                            "stage_seconds": self.extractor.last_result.timings,
                            "container_call_number": self.calls,
                            "remote_wall_seconds": perf_counter() - started}}

    @modal.method()
    def diagnose(self, payload, match_id, compare_reference=True):
        return self._diagnose(payload, match_id, compare_reference)

    @modal.method()
    def diagnose_pair(self, payload_a, payload_b):
        """A-B-A on one warm worker; no cross-container state-isolation claim."""
        import numpy as np

        results = []
        for payload, compare in [(payload_a, True), (payload_b, True), (payload_a, False)]:
            result = self._diagnose(payload, payload["match_id"], compare)
            results.append(result)
            if compare and not result["gate"]["passed"]:
                return results
        results[-1]["repeated_A_after_B_equal"] = bool(np.array_equal(results[0]["features"], results[-1]["features"]))
        return results

    def _diagnose(self, payload, match_id, compare_reference=True):
        """Private bounded validation: same adapter plus a fresh research reference."""
        import hashlib
        import importlib.metadata

        import numpy as np
        from matchpulse.features import MatchFeatureExtractor

        from backend.ml_inference.transport import decode_request
        from backend.ml_inference.validation import validate_features, validate_match_id

        validate_match_id(match_id)
        started = perf_counter()
        _, frames, audio = decode_request(payload, expected_id=match_id, max_bytes=self.max_window_bytes)
        decode_seconds = perf_counter() - started
        before = hashlib.sha256(memoryview(frames).cast("B")).hexdigest()
        audio_before = hashlib.sha256(memoryview(audio).cast("B")).hexdigest()
        self.extractor.clear_cache()
        self.calls += 1
        t = perf_counter()
        features = self.extractor.extract(match_id, frames, audio)
        extraction_seconds = perf_counter() - t
        result = self.extractor.last_result
        diagnostics = result.diagnostics
        detector_details = detector_runtime(self.extractor._extractor.detector, self.fp16)
        gate = None
        if compare_reference:
            source = self.extractor._extractor
            reference = MatchFeatureExtractor(
                detector=source.detector, detector_config=source.detector_config, config=source.config
            )
            t = perf_counter()
            expected = reference.extract(frames, fps=15, audio=audio, audio_sample_rate=16000)
            validate_features(expected, missing_audio=False)
            reference_seconds = perf_counter() - t
            close = np.isclose(features, expected, atol=2e-5, rtol=1e-5)
            slots_equal = np.array_equal(diagnostics["slot_ids"], reference.last_result.diagnostics["slot_ids"])
            teams_equal = np.array_equal(features[:, :198].reshape(75, 22, 9)[:, :, 8],
                                        expected[:, :198].reshape(75, 22, 9)[:, :, 8])
            gate = {
                "passed": bool(close.all() and slots_equal and teams_equal),
                "atol": 2e-5, "rtol": 1e-5,
                "max_absolute_difference": float(np.max(np.abs(features - expected))),
                "elements_outside_tolerance": int((~close).sum()),
                "slot_ids_equal": bool(slots_equal), "teams_equal": bool(teams_equal),
                "audio_equal": bool(np.array_equal(features[:, 210:], expected[:, 210:])),
                "camera_equal": bool(np.allclose(features[:, 205:210], expected[:, 205:210], atol=2e-5, rtol=1e-5)),
                "reference_shape": list(expected.shape), "reference_dtype": str(expected.dtype),
                "camera_cuts_equal": bool(np.array_equal(features[:, 208], expected[:, 208])),
                "reference_seconds": reference_seconds,
                "reference": "Fresh research MatchFeatureExtractor, identical model/config/GPU/precision",
            }
        after = hashlib.sha256(memoryview(frames).cast("B")).hexdigest()
        return {
            "match_id": match_id, "features": features,
            "runtime": {**self.runtime, **detector_details},
            "initialization_seconds": self.initialization_seconds, "container_call_number": self.calls,
            "decode_seconds": decode_seconds, "extraction_seconds": extraction_seconds,
            "detector_load_seconds": self.extractor._extractor.model_load_seconds,
            "stage_seconds": result.timings, "input_sha256": before,
            "input_unchanged": before == after, "gate": gate,
            "audio_sha256": audio_before,
            "audio_unchanged": audio_before == hashlib.sha256(memoryview(audio).cast("B")).hexdigest(),
            "audio_available_intervals": int(features[:, 214].sum()),
            "audio_feature_nonzero": bool(np.any(features[:, 210:214] != 0)),
            "visible_player_mean": float(features[:, :198].reshape(75, 22, 9)[:, :, 7].sum(axis=1).mean()),
            "ball_visible_samples": int(features[:, 203].sum()),
            "frames_inferred": diagnostics["detector_frames_inferred"],
            "versions": {name: importlib.metadata.version(name)
                         for name in ["numpy", "av", "ultralytics", "opencv-python", "scipy"]},
            "remote_wall_seconds": perf_counter() - started,
        }


@app.cls(image=image, cpu=2, memory=4096, volumes={"/models": models},
         max_containers=1, min_containers=0, buffer_containers=0,
         scaledown_window=SCALEDOWN, timeout=CLASSIFIER_TIMEOUT,
         retries=0, include_source=False)
class ClassifierWorker:
    checkpoint_name: str = modal.parameter(default="classifier.pt")

    @modal.enter()
    def load(self):
        from backend.ml_inference.classifiers import ResearchInterestScorer

        root = Path("/models").resolve()
        target = (root / self.checkpoint_name).resolve()
        if not target.is_relative_to(root) or target == root:
            raise ValueError("Classifier path must remain inside the inference model Volume")
        models.reload()
        self.scorer = ResearchInterestScorer(target, device="cpu").prepare()

    @modal.method()
    def ready(self):
        return {"schema": "matchpulse-215-v1", "input_shape": [75, 215],
                "audio_required": True, "model_input_size": 215}

    @modal.method()
    def predict(self, features):
        return self.scorer.predict_scores(features)
