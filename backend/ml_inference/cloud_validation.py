"""Bounded, explicitly authorized deployment/real-footage validation controller.

Only matchpulse-inference can be addressed. Never imports research orchestration.
Private local artifacts and the isolated client environment are ignored by Git.
"""

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

from .config import APP_NAME

ROOT = Path(__file__).resolve().parent
ARTIFACTS = ROOT / "artifacts/t4-av-validation"
RATES = {"t4": 0.000164, "cpu": 0.0000131, "memory_gib": 0.00000222}
MAX_GPU_RATE = RATES["t4"] + 4 * RATES["cpu"] + 8 * RATES["memory_gib"]


def save(name, value):
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    path = ARTIFACTS / name
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


class TaskBudget:
    def __init__(self):
        path = ARTIFACTS / "budget.json"
        self.data = json.loads(path.read_text()) if path.exists() else {
            "ceiling_usd": 5.0, "entries": [], "rates": RATES,
            "pricing_source": "https://modal.com/pricing",
            "note": "Controller estimates only; not provider billing or a provider-enforced cap",
        }
        if self.data["ceiling_usd"] != 5:
            raise RuntimeError("Unexpected validation budget ceiling")
        previous = ROOT / "artifacts/cloud-validation/budget.json"
        self.data["prior_task_estimate_usd"] = (json.loads(previous.read_text())["estimated_usd"]
                                                if previous.exists() else 0)

    def reserve(self, name, amount):
        if not math.isfinite(amount) or amount <= 0:
            raise ValueError("Cloud reservation must be finite and positive")
        total = sum(row["estimated_usd"] for row in self.data["entries"])
        if total + amount > 5:
            raise RuntimeError("$5 validation estimate exhausted; do not launch more cloud work")
        row = {"name": name, "estimated_usd": amount, "state": "reserved", "time": time.time()}
        self.data["entries"].append(row)
        self.flush()
        return row

    def settle(self, row, elapsed):
        if not math.isfinite(elapsed) or elapsed < 0:
            raise ValueError("Cloud elapsed time must be finite and nonnegative")
        row.update(state="returned", elapsed_seconds=elapsed,
                   estimated_usd=min(row["estimated_usd"], (elapsed + 30) * MAX_GPU_RATE))
        self.flush()

    def flush(self):
        self.data["estimated_usd"] = sum(row["estimated_usd"] for row in self.data["entries"])
        self.data["combined_inference_estimate_usd"] = self.data["estimated_usd"] + self.data["prior_task_estimate_usd"]
        save("budget.json", self.data)


def environment():
    env = dict(os.environ)
    env.update({
        "MATCHPULSE_ML_MODE": "features_mock", "MATCHPULSE_ML_GPU": "T4",
        "MATCHPULSE_ML_WORKER_CONCURRENCY": "1", "MATCHPULSE_ML_MAX_INFLIGHT": "1",
        "MATCHPULSE_ML_SCALEDOWN_SECONDS": "5", "MATCHPULSE_ML_WORKER_TIMEOUT_SECONDS": "180",
        "MATCHPULSE_ML_CALL_TIMEOUT_SECONDS": "300", "MATCHPULSE_ML_REQUEST_TIMEOUT_SECONDS": "600",
        "MATCHPULSE_ML_WEIGHTS": str(ROOT.parents[2] / "cheap-classifier-model-research/yolo26s.pt"),
        "PYTHONIOENCODING": "utf-8",
    })
    return env


def deploy():
    if APP_NAME != "matchpulse-inference":
        raise RuntimeError("Unexpected deployment target")
    budget = TaskBudget()
    if sum(row["name"] == "image-build-and-deployment" for row in budget.data["entries"]) >= 2:
        raise RuntimeError("Two bounded T4 deployment attempts already used; inspect failures")
    budget.reserve("image-build-and-deployment", 0.60)
    attempt = sum(row["name"] == "image-build-and-deployment" for row in budget.data["entries"])
    started = time.perf_counter()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    # No footage is uploaded by deploy. Image inputs exclude all local artifacts/envs.
    log_name = f"deployment-{attempt:03d}.log"
    with (ARTIFACTS / log_name).open("w", encoding="utf-8") as log:
        result = subprocess.run(
            [sys.executable, "-B", "-m", "modal", "deploy", "-m", "backend.ml_inference.modal_app"],
            cwd=ROOT.parents[1], env=environment(), stdout=log, stderr=subprocess.STDOUT,
            timeout=1200, check=False,
        )
    save("deployment.json", {"app": APP_NAME, "exit_code": result.returncode,
                             "wall_seconds": time.perf_counter() - started,
                             "gpu": "T4", "max_containers": 1, "min_containers": 0,
                             "scaledown_seconds": 5, "log": log_name})
    if result.returncode:
        raise RuntimeError("Inference deployment failed; inspect the owned deployment log")
    print("Deployed matchpulse-inference; no footage processing started", flush=True)


def load_football_window(path, start):
    """PTS interval-centre sampling, with original pixels and no audio transfer."""
    import av
    import numpy as np

    targets = start + (np.arange(75, dtype=np.float64) + 0.5) / 15
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        origin = float((stream.start_time or 0) * stream.time_base)
        duration = (float(stream.duration * stream.time_base) if stream.duration is not None
                    else container.duration / av.time_base)
        if duration < start + 5 - 1e-6:
            raise ValueError("Source does not cover five complete seconds")
        if start:
            container.seek(int((origin + max(0, start - 0.25)) / stream.time_base),
                           stream=stream, backward=True)
        output = np.empty((75, stream.height, stream.width, 3), dtype=np.uint8)
        previous, source_pts, index = None, [], 0
        for frame in container.decode(stream):
            if frame.pts is None or frame.is_corrupt:
                raise ValueError("Invalid source video observation")
            pts = float(frame.pts * stream.time_base) - origin
            while index < 75 and targets[index] < pts - 1e-8:
                if previous is None or targets[index] - previous[0] > 0.21:
                    raise ValueError("Source coverage gap at a target timestamp")
                output[index] = previous[1].to_ndarray(format="rgb24")
                source_pts.append(previous[0])
                index += 1
            if index == 75:
                break
            previous = (pts, frame)
        if index < 75 and previous is not None:
            coverage = previous[0] + float(previous[1].duration * stream.time_base)
            while index < 75 and targets[index] < coverage + 1e-8:
                output[index] = previous[1].to_ndarray(format="rgb24")
                source_pts.append(previous[0])
                index += 1
        if index != 75:
            raise ValueError("Source ends before the final interval centre")
    return output, {
        "source_basename": path.name, "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "start_seconds": start, "shape": list(output.shape), "dtype": str(output.dtype),
        "sampling": "latest source PTS <= start+(i+0.5)/15; original RGB pixels",
        "target_timestamps": targets.tolist(), "source_timestamps": source_pts,
        "input_sha256": hashlib.sha256(memoryview(output).cast("B")).hexdigest(),
        "audio": "not supplied; research missing-audio representation",
    }


class BudgetedMethod:
    def __init__(self, method, budget, name):
        self.method, self.budget, self.name = method, budget, name

    def spawn(self, *args):
        row = self.budget.reserve(self.name, (180 + 300 + 30) * MAX_GPU_RATE)
        started = time.perf_counter()
        handle = self.method.spawn(*args)
        row["call_id"] = handle.object_id
        self.budget.flush()
        budget = self.budget

        class Handle:
            def get(self, timeout):
                try:
                    result = handle.get(timeout=timeout)
                except Exception as exc:
                    row.update(state="failed-or-unconfirmed", error_type=type(exc).__name__)
                    budget.flush()
                    raise
                budget.settle(row, time.perf_counter() - started)
                return result

            def cancel(self, **kwargs):
                return handle.cancel(**kwargs)

        return Handle()


def validate():
    from .t4_validation import validate as run

    run()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["deploy", "validate"])
    parser.add_argument("--allow-cloud", action="store_true")
    args = parser.parse_args()
    if not args.allow_cloud:
        parser.error("Cloud execution must be explicitly authorized")
    if args.action == "deploy":
        deploy()
    else:
        try:
            validate()
        except Exception as exc:
            # Keep actionable metadata without copying exception text, SDK blob
            # URLs, credentials or footage into durable artifacts.
            save("failure.json", {"passed": False, "error_type": type(exc).__name__,
                                  "time": time.time(),
                                  "note": "Inspect private app logs and budget call IDs; do not retry blindly"})
            raise


if __name__ == "__main__":
    main()
