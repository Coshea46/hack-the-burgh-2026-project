"""Bounded, seven-source browser demo; cloud inference requires explicit opt-in."""

import argparse
import asyncio
import json
import logging
import math
import os
import time
from pathlib import Path

from backend.main import AppController
from backend.ml_inference.overhaul_cloud import environment
from backend.ml_inference.replay_contract import MATCHES_PER_GPU, MAX_WORKER_RATE
from backend.replay import SessionConfig, SourceRegistry

ARTIFACTS = Path(__file__).resolve().parent / "ml_inference/artifacts/product-polish"
TASK_CEILING_USD = 2.0
MODEL_VERSION = "gru-stage1-02de8309"


def write_receipt(directory, name, value):
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / name
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(target)


class DemoBudget:
    """Separate, persistent $2 verification allowance; uncertain stops retain reserves."""

    def __init__(self, directory=ARTIFACTS):
        self.directory = directory
        target = directory / "budget.json"
        self.data = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {
            "ceiling_usd": TASK_CEILING_USD, "entries": [],
            "note": "Product-polish verification estimate, not provider billing or a billing cap",
        }
        if self.data.get("ceiling_usd") != TASK_CEILING_USD:
            raise ValueError("Unexpected verification budget ceiling")

    def reserve(self, estimate):
        if not math.isfinite(estimate) or estimate <= 0:
            raise ValueError("Reservation must be finite and positive")
        if sum(row["estimated_usd"] for row in self.data["entries"]) + estimate > TASK_CEILING_USD:
            raise RuntimeError("The $2 product-verification allowance is exhausted")
        row = {"at": time.time(), "state": "reserved", "estimated_usd": estimate}
        self.data["entries"].append(row)
        self.flush()
        return row

    def settle(self, row, elapsed, workers, *, started, stopped):
        if not stopped:
            return
        row.update(state="stopped", elapsed_seconds=elapsed,
                   estimated_usd=min(row["estimated_usd"], (elapsed + 30) * workers * MAX_WORKER_RATE)
                   if started else 0)
        self.flush()

    def flush(self):
        self.data["estimated_usd"] = sum(row["estimated_usd"] for row in self.data["entries"])
        write_receipt(self.directory, "budget.json", self.data)


def configuration(matches, seconds, offline):
    if type(matches) is not int or not 1 <= matches <= 7:
        raise ValueError("Choose one to seven matches")
    if type(seconds) is not int or not 30 <= seconds <= 180:
        raise ValueError("Choose 30 to 180 seconds")
    workers = math.ceil(matches / MATCHES_PER_GPU)
    allowance = (seconds + 330) * workers * MAX_WORKER_RATE
    registry = SourceRegistry.from_env({"MATCHPULSE_MATCH_COUNT": str(matches),
        "MATCHPULSE_OFFSETS_JSON": json.dumps({f"cam-{i}": 120 for i in range(1, matches + 1)})})
    config = SessionConfig(monitor=not offline, mode="disabled" if offline else "real",
        model_version="disabled" if offline else MODEL_VERSION,
        checkpoint=None if offline else f"{MODEL_VERSION}/classifier.pt",
        max_duration_seconds=seconds, max_estimated_cost_usd=allowance + 0.000001,
        gpu_workers=workers, max_restarts=0)
    return registry, config, allowance


async def serve(args):
    registry, config, allowance = configuration(args.matches, args.seconds, args.offline)
    if not args.offline:
        os.environ.update(environment())
    os.environ["MATCHPULSE_ALLOWED_ORIGINS"] = (
        f"http://localhost:{args.frontend_port},http://127.0.0.1:{args.frontend_port}")
    budget = None if args.offline else DemoBudget()
    reservation = None if budget is None else budget.reserve(allowance)
    controller = AppController(registry=registry, config=config, host="127.0.0.1", port=args.port)
    session = controller.session
    before = time.perf_counter()
    server = asyncio.create_task(controller.start())
    observations = []
    print(f"MatchPulse: {args.matches} distinct sources on 127.0.0.1:{args.port}; "
          f"{'monitoring disabled' if args.offline else 'real model'}; limit {args.seconds}s", flush=True)
    try:
        while time.perf_counter() - before < args.seconds:
            await asyncio.sleep(min(2, max(0, args.seconds - (time.perf_counter() - before))))
            if server.done():
                await server
                break
            observations.append({"elapsed": time.perf_counter() - before,
                "state": session.state, "position": session.position, "playing": session.playing,
                "epoch": session.clock_epoch, "current_match_id": session.director.current_match_id,
                "director": session.director.state(now=session.now(), playback_position=session.position),
                "clients": len(session.clients), "metrics": dict(session.metrics)})
            write_receipt(ARTIFACTS, "browser-progress.json", {"observations": observations})
    finally:
        # Revoke inference before draining a browser socket. A slow viewer must
        # never extend the paid monitoring lifetime while the HTTP server exits.
        await session.close()
        server.cancel()
        socket_shutdown = "completed"
        try:
            await asyncio.wait_for(asyncio.gather(server, return_exceptions=True), timeout=8)
        except TimeoutError:
            socket_shutdown = "timed_out"
        elapsed = time.perf_counter() - before
        report = {"mode": config.mode, "matches": args.matches,
            "match_ids": [source.match_id for source in registry.sources],
            "socket_shutdown": socket_shutdown,
            "observations": observations, "metrics": session.metrics,
            "worker_health": session.worker_health, "elapsed_seconds": elapsed}
        write_receipt(ARTIFACTS, "browser.json", report)
        if budget:
            started = session.metrics.get("reserved_compute_usd", 0) > 0
            stopped = not started or session.metrics.get("worker_stop_succeeded") is True
            budget.settle(reservation, elapsed, config.gpu_workers, started=started, stopped=stopped)
        print("Demo stopped; owned worker stop confirmed:",
              session.metrics.get("worker_stop_succeeded", "no worker started"), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matches", type=int, choices=range(1, 8), default=7)
    parser.add_argument("--seconds", type=int, choices=range(30, 181), default=120)
    parser.add_argument("--port", type=int, default=8030)
    parser.add_argument("--frontend-port", type=int, default=3030)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--allow-cloud", action="store_true", help="Use the installed real GRU")
    modes.add_argument("--offline", action="store_true", help="Play sources without GPU monitoring")
    args = parser.parse_args()
    if not (1024 <= args.port <= 65535 and 1024 <= args.frontend_port <= 65535
            and args.port != args.frontend_port):
        parser.error("Choose distinct backend/frontend ports between 1024 and 65535")
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(serve(args))


if __name__ == "__main__":
    main()
