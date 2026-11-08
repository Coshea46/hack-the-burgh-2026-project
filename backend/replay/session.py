"""Nonblocking replay lifecycle, viewer lease and compact-score orchestration."""

import asyncio
import json
import logging
import math
import os
import re
import time
import uuid
from dataclasses import dataclass

from .director import DIRECTOR_MODES, Director
from .sources import number

try:
    from ..ml_inference.replay_contract import MATCHES_PER_GPU, MAX_GPU_WORKERS
except ImportError:
    from ml_inference.replay_contract import MATCHES_PER_GPU, MAX_GPU_WORKERS

logger = logging.getLogger(__name__)


def worker_diagnostics(snapshot):
    """Retain bounded protocol labels, never exception messages or source URLs."""
    states = {"starting", "ready", "running", "error", "stopped"}
    reasons = {"checkpoint_unavailable", "processing_error", "shard_error", "shard_stopped",
               "session_limit", "lease_expired", "control_stopped", "all_sources_ended", "paused"}
    phases = {"checkpoint", "resolve", "volume_reload", "validate", "load", "reader", "open", "decode", "audio", "audio_window", "detector",
              "visual", "assembly", "classifier", "scoring", "publication", "control"}
    codes = {"checkpoint_path_escape", "checkpoint_file_invalid", "checkpoint_file_too_large",
             "checkpoint_metadata_invalid", "checkpoint_schema_mismatch", "checkpoint_architecture_mismatch",
             "checkpoint_model_structure", "checkpoint_normalization_provenance", "checkpoint_normalization_invalid",
             "checkpoint_dataset_provenance", "checkpoint_threshold_invalid", "checkpoint_version_invalid",
             "checkpoint_audio_schema", "checkpoint_resolve_failed", "checkpoint_volume_reload_failed",
             "checkpoint_load_failed", "checkpoint_validate_failed"}

    def error_type(value):
        return (value if isinstance(value, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", value)
                and (value.endswith(("Error", "Exception"))
                     or value in ("KeyboardInterrupt", "InvalidStatusCode", "InvalidHandshake")) else None)

    def labels(value):
        if not isinstance(value, dict):
            value = {}
        reason = value.get("reason")
        state, phase, code = value.get("state"), value.get("error_phase"), value.get("error_code")
        return {"state": state if isinstance(state, str) and state in states else None,
                "reason": reason if isinstance(reason, str) and reason in reasons else error_type(reason),
                "error_type": error_type(value.get("error_type")),
                "error_phase": phase if isinstance(phase, str) and phase in phases else None,
                "error_code": code if isinstance(code, str) and code in codes else None}

    if not isinstance(snapshot, dict):
        snapshot = {}
    result = {"worker_" + key: value for key, value in labels(snapshot).items()}
    shards = snapshot.get("shard_errors", {})
    result["worker_shard_errors"] = {key: labels(shards[key]) for key in map(str, range(MAX_GPU_WORKERS)) if key in shards
                                      and isinstance(shards[key], dict)} if isinstance(shards, dict) else {}
    return result


def transient_transport_error(snapshot):
    """Only explicitly transport-labelled failures may restart a worker group."""
    def transport(record):
        return (isinstance(record, dict) and record.get("reason") == "processing_error"
                and record.get("error_phase") in ("control", "publication"))

    if transport(snapshot):
        return True
    shards = snapshot.get("shard_errors")
    return (snapshot.get("reason") == "shard_error" and isinstance(shards, dict)
            and 1 <= len(shards) <= MAX_GPU_WORKERS and set(shards) <= set(map(str, range(MAX_GPU_WORKERS)))
            and all(transport(record) for record in shards.values()))


@dataclass(frozen=True)
class SessionConfig:
    monitor: bool = False
    mode: str = "disabled"
    model_version: str = "disabled"
    checkpoint: str | None = None
    max_duration_seconds: float = 300
    max_estimated_cost_usd: float = 1
    heartbeat_seconds: float = 5
    pause_idle_seconds: float = 10
    poll_seconds: float = 0.1
    control_seconds: float = 0.25
    max_restarts: int = 2
    mock_scores: dict | None = None
    gpu_workers: int | None = None
    shutdown_rpc_seconds: float = 5
    replay_transport: str = "websocket"
    director_mode: str = "balanced"
    director_emergency_enabled: bool = False
    director_emergency_margin: float = 0.50

    def __post_init__(self):
        if not isinstance(self.monitor, bool):
            raise TypeError("monitor must be an explicit boolean")
        if self.monitor and self.mode not in ("real", "features_mock"):
            raise ValueError("Monitoring requires explicit MATCHPULSE_ML_MODE=real or features_mock")
        if not self.monitor and self.mode != "disabled":
            raise ValueError("Disabled monitoring must use disabled mode")
        if self.monitor and self.mode == "real" and not self.checkpoint:
            raise ValueError("Real monitoring requires MATCHPULSE_ML_CHECKPOINT")
        if (not isinstance(self.model_version, str)
                or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,160}", self.model_version)):
            raise ValueError("Invalid model version")
        number(self.max_duration_seconds, "max_duration_seconds", minimum=10, maximum=3600)
        number(self.max_estimated_cost_usd, "max_estimated_cost_usd", minimum=0.01, maximum=10)
        number(self.heartbeat_seconds, "heartbeat_seconds", minimum=1, maximum=30)
        number(self.pause_idle_seconds, "pause_idle_seconds", minimum=1, maximum=30)
        number(self.poll_seconds, "poll_seconds", minimum=0.05, maximum=2)
        number(self.control_seconds, "control_seconds", minimum=0.1, maximum=2)
        number(self.shutdown_rpc_seconds, "shutdown_rpc_seconds", minimum=0.01, maximum=30)
        if not isinstance(self.max_restarts, int) or isinstance(self.max_restarts, bool) or not 0 <= self.max_restarts <= 3:
            raise ValueError("max_restarts must be between 0 and 3")
        if self.mock_scores is not None:
            if self.mode != "features_mock" or not isinstance(self.mock_scores, dict):
                raise ValueError("mock_scores is permitted only in explicit features_mock mode")
            for match_id, score in self.mock_scores.items():
                if not isinstance(match_id, str):
                    raise TypeError("Mock score keys must be match IDs")
                number(score, "mock_score", maximum=1)
        if self.gpu_workers is not None and (type(self.gpu_workers) is not int or not 1 <= self.gpu_workers <= MAX_GPU_WORKERS):
            raise ValueError(f"gpu_workers must be between 1 and {MAX_GPU_WORKERS}")
        if self.replay_transport not in ("websocket", "dict"):
            raise ValueError("MATCHPULSE_REPLAY_TRANSPORT must be websocket or dict")
        if not isinstance(self.director_mode, str) or self.director_mode not in DIRECTOR_MODES:
            raise ValueError("MATCHPULSE_DIRECTOR_MODE must be relaxed, balanced or all_action")
        if type(self.director_emergency_enabled) is not bool:
            raise TypeError("director_emergency_enabled must be boolean")
        number(self.director_emergency_margin, "director_emergency_margin", minimum=0.05, maximum=1)

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        flag = env.get("MATCHPULSE_MONITOR", "false").lower()
        if flag not in ("true", "false"):
            raise ValueError("MATCHPULSE_MONITOR must be true or false")
        enabled = flag == "true"
        mode = env.get("MATCHPULSE_ML_MODE", "") if enabled else "disabled"
        checkpoint = env.get("MATCHPULSE_ML_CHECKPOINT") or None
        version = env.get("MATCHPULSE_MODEL_VERSION") or (checkpoint if mode == "real" else
                                                        "features-mock-v1" if enabled else "disabled")
        raw_mock = env.get("MATCHPULSE_MOCK_SCORES_JSON")
        emergency_flag = env.get("MATCHPULSE_DIRECTOR_EMERGENCY_ENABLED", "false").lower()
        if emergency_flag not in ("true", "false"):
            raise ValueError("MATCHPULSE_DIRECTOR_EMERGENCY_ENABLED must be true or false")
        try:
            mock_scores = json.loads(raw_mock) if raw_mock and enabled else None
        except ValueError as exc:
            raise ValueError("Invalid MATCHPULSE_MOCK_SCORES_JSON") from exc
        return cls(monitor=enabled, mode=mode, model_version=version, checkpoint=checkpoint,
                   max_duration_seconds=float(env.get("MATCHPULSE_SESSION_SECONDS", "300")),
                   max_estimated_cost_usd=float(env.get("MATCHPULSE_SESSION_BUDGET_USD", "1")),
                   mock_scores=mock_scores,
                   gpu_workers=int(env["MATCHPULSE_GPU_WORKERS"]) if env.get("MATCHPULSE_GPU_WORKERS") else None,
                   replay_transport=env.get("MATCHPULSE_REPLAY_TRANSPORT") or "websocket",
                   director_mode=env.get("MATCHPULSE_DIRECTOR_MODE") or "balanced",
                   director_emergency_enabled=emergency_flag == "true",
                   director_emergency_margin=float(env.get("MATCHPULSE_DIRECTOR_EMERGENCY_MARGIN", "0.50")))


class ReplaySession:
    """One shared replay session; the first connected viewer owns its clock.

    SDK work runs outside socket handlers in two sequential background loops.
    There is at most one score read and one control/lifecycle RPC in flight.
    The worker receives the last reported media position, never extrapolation.
    """

    def __init__(self, registry, *, config=None, bridge=None, publish=None,
                 now=time.time, monotonic=time.monotonic, session_id=None):
        self.registry, self.config, self.bridge = registry, config or SessionConfig(), bridge
        self.publish = publish or (lambda payload: None)
        self.now, self.monotonic = now, monotonic
        self.session_id = session_id or uuid.uuid4().hex
        self.sequence = 0
        self.sources = ()
        self.director = None
        self.clients = []
        self.controller = None
        self.position, self.playing, self.rate, self.stalled = 0.0, False, 1.0, False
        self.clock_epoch = 0
        self.state = "waiting" if self.config.monitor else "disabled"
        self.error_code = None
        self.last_report_at = None
        self._paused_at = None
        self._ready_at = None
        self._monitor_started_at = None
        self._handle = None
        self._stopping_handle = None
        self._start_inflight = None
        self._worker_ready = False
        self._stop_requested = False
        self._restart_after_seek = False
        self._closing = False
        self._closed = False
        self._ended = False
        self._finished = False
        self._finished_reason = "session_limit_reached"
        self._restarts = 0
        self._retry_at = 0.0
        self._sources_changed = True
        self._tasks = []
        self._last_recommendation = None
        self._last_ack_sequence = None
        self._unplayable = set()
        self._reserved_compute_usd = 0.0
        self._selection_pending_until = 0.0
        self.metrics = {"recommendations": 0, "director_seconds": 0.0, "worker_failures": 0,
                        "control_rpc_count": 0, "control_rpc_seconds": 0.0,
                        "score_rpc_count": 0, "score_rpc_seconds": 0.0,
                        "replay_transport": self.config.replay_transport,
                        "owned_stop_method": ("websocket_graceful" if self.config.replay_transport == "websocket"
                                              else "modal_input_cancel")}
        self.worker_health = {}

    async def initialize(self):
        self.sources = await asyncio.to_thread(self.registry.resolve)
        if self.config.gpu_workers is not None and self.config.gpu_workers > len(self.sources):
            raise ValueError("gpu_workers cannot exceed registered source count")
        self.director = Director([source.match_id for source in self.sources],
                                 session_id=self.session_id, model_version=self.config.model_version,
                                 mode=self.config.mode, director_mode=self.config.director_mode,
                                 emergency_enabled=self.config.director_emergency_enabled,
                                 emergency_margin=self.config.director_emergency_margin)
        self._model_health = dict(self.director.healthy)
        if self.config.mock_scores is not None and set(self.config.mock_scores) - set(self.director.match_ids):
            raise ValueError("Mock score configured for an unregistered match")
        if self.config.monitor and self.bridge is None:
            # Default startup never imports or authenticates the Modal SDK.
            if self.config.replay_transport == "websocket":
                try:
                    from ..ml_inference.replay_ws_client import ReplayWebSocketClient
                except ImportError:
                    from ml_inference.replay_ws_client import ReplayWebSocketClient
                self.bridge = ReplayWebSocketClient.from_env()
            else:
                try:
                    from ..ml_inference.replay_client import ReplayClient
                except ImportError:
                    from ml_inference.replay_client import ReplayClient
                self.bridge = ReplayClient()
        return self

    def _next_sequence(self):
        self.sequence += 1
        return self.sequence

    def controls_enabled(self, client_id):
        return client_id == self.controller

    def snapshot(self, client_id=None):
        result = {"type": "session", "protocol_version": 1,
                  "session_id": self.session_id, "sequence": self.sequence,
                  "state": self.state, "mode": self.config.mode,
                  "model_version": self.config.model_version, "server_time": self.now(),
                  "playback": {"position": self.position, "playing": self.playing,
                               "rate": self.rate, "clock_epoch": self.clock_epoch},
                  "matches": [source.public_spec(self.director.healthy[source.match_id])
                              for source in self.sources],
                  "current_match_id": self.director.current_match_id,
                  "auto_enabled": self.director.auto_enabled,
                  "manual_hold_until": self.director.manual_hold_until,
                  "director": self.director.state(now=self.now(), playback_position=self.position)}
        if client_id is not None:
            result["controls_enabled"] = self.controls_enabled(client_id)
        if self.error_code is not None:
            result["error_code"] = self.error_code
        return result

    def _publish_session(self):
        self._next_sequence()
        self.publish(self.snapshot())

    def _set_state(self, state, error_code=None):
        if self.state != state or self.error_code != error_code:
            self.state, self.error_code = state, error_code
            self._publish_session()

    def connect(self, client_id):
        if client_id not in self.clients:
            self.clients.append(client_id)
        if self.controller is None:
            self.controller = client_id
        self._next_sequence()
        return self.snapshot(client_id)

    def disconnect(self, client_id):
        if client_id in self.clients:
            self.clients.remove(client_id)
        if self.controller == client_id:
            self.controller = self.clients[0] if self.clients else None
            self.playing = False
            self.last_report_at = None
            self._stop_requested = True
            self._set_state("waiting" if self.config.monitor and not self._finished else self.state)
            self._publish_session()

    def _error(self, code):
        return {"type": "error", "protocol_version": 1, "session_id": self.session_id,
                "sequence": self._next_sequence(), "code": code}

    def receive(self, client_id, message):
        """Validate and update local state only; no decoder, SDK or network I/O."""
        if not isinstance(message, dict) or message.get("session_id") != self.session_id:
            return self._error("session_mismatch")
        if message.get("type") == "ack":
            return self._receive_ack(client_id, message)
        if not self.controls_enabled(client_id):
            return self._error("viewer_in_use")
        kind = message.get("type")
        if kind == "playback":
            return self._receive_playback(message)
        if kind == "select":
            match_id = message.get("match_id")
            if not isinstance(match_id, str) or match_id not in self.director.records:
                return self._error("unknown_match")
            self.director.manual_select(match_id, now=self.now(), playback_position=self.position)
            self._selection_pending_until = self.monotonic() + 2
            self._last_recommendation = None
            self._publish_session()
            return None
        if kind == "auto":
            enabled = message.get("enabled")
            if not isinstance(enabled, bool):
                return self._error("invalid_auto")
            self.director.set_auto(enabled)
            self._last_recommendation = None
            self._publish_session()
            return None
        if kind == "director_mode":
            try:
                self.director.set_mode(message.get("mode"))
            except (ValueError, TypeError):
                return self._error("invalid_director_mode")
            self._last_recommendation = None
            self._publish_session()
            return None
        return self._error("unknown_message")

    def _valid_recommendation(self, recommendation, *, position=None):
        position = self.position if position is None else position
        return (not self._finished and not self._stop_requested and not self._closing
                and self.state in ("running", "degraded", "paused")
                and recommendation is not None and recommendation.get("clock_epoch") == self.clock_epoch
                and self.director.healthy.get(recommendation.get("selected_match_id"), False)
                and recommendation.get("valid_until", 0) >= self.now()
                and recommendation.get("observation_end", math.inf) <= position + 0.05
                and position - recommendation.get("observation_end", 0) <= self.director.maximum_playback_lag)

    def _receive_ack(self, client_id, message):
        recommendation = self._last_recommendation
        if (not self._valid_recommendation(recommendation) or type(message.get("sequence")) is not int
                or message.get("sequence") != recommendation["sequence"]
                or message.get("clock_epoch") != self.clock_epoch
                or message.get("match_id") != recommendation["selected_match_id"]):
            return self._error("stale_ack")
        if self.controls_enabled(client_id) and self._last_ack_sequence == recommendation["sequence"]:
            return None
        delivered = max(0, self.now() - recommendation["emitted_at"])
        self.metrics["last_ack"] = {"sequence": recommendation["sequence"],
                                    "match_id": recommendation["selected_match_id"],
                                    "controller": self.controls_enabled(client_id),
                                    "delivery_seconds": delivered,
                                    "observation_to_ack_seconds": recommendation["latency_seconds"] + delivered,
                                    "server_received_at": self.now()}
        if self.controls_enabled(client_id):
            if recommendation["selected_match_id"] != self.director.current_match_id:
                self.director.commit_selection(recommendation["selected_match_id"], now=self.now(),
                    kind=recommendation.get("selection_kind", "automatic"),
                    reason=recommendation.get("selection_reason", "challenger_confirmed"),
                    playback_position=self.position,
                    score=recommendation["scores"].get(recommendation["selected_match_id"]))
                self._publish_session()
            self._last_ack_sequence = recommendation["sequence"]
            self._selection_pending_until = self.monotonic() + 2
        return None

    def _receive_playback(self, message):
        if not isinstance(message.get("match_id"), str) or message.get("match_id") not in self.director.records:
            return self._error("unknown_match")
        try:
            position = number(message.get("position"), "position", maximum=86400)
            rate = number(message.get("rate"), "rate", minimum=0.25, maximum=4)
        except ValueError:
            return self._error("invalid_playback")
        if any(not isinstance(message.get(key, False), bool) for key in
               ("playing", "stalled", "available", "ended")):
            return self._error("invalid_playback")
        now = self.monotonic()
        previous_health = self.director.healthy.copy()
        # A recommendation can be discarded by the player (expiry, unavailable
        # source, manual hold). Its actual clock remains authoritative. Allow a
        # brief source-transition interval following a manual pick/ACK.
        if (message["match_id"] != self.director.current_match_id
                and now >= self._selection_pending_until
                and message.get("available", True) and not message.get("stalled", False)):
            proposal = self._last_recommendation
            automatic = (self.director.auto_enabled and self._valid_recommendation(proposal, position=position)
                         and message.get("available", True) and not message.get("stalled", False)
                         and proposal["selected_match_id"] == message["match_id"])
            self.director.commit_selection(message["match_id"], now=self.now(),
                kind=proposal.get("selection_kind", "automatic") if automatic else "playback",
                reason=proposal.get("selection_reason") if automatic else "playback_feedback",
                playback_position=position,
                score=proposal["scores"].get(message["match_id"]) if automatic else None)
            self._publish_session()
        jumped = False
        if self.last_report_at is not None:
            elapsed = max(0, now - self.last_report_at)
            movement = position - self.position
            jumped = movement < -0.001 or movement > max(2, elapsed * max(rate, self.rate) + 1)
        self.position, self.rate = position, rate
        self.stalled = message.get("stalled", False) or not message.get("available", True)
        self.playing = message.get("playing", False) and not self.stalled and not message.get("ended", False)
        self.last_report_at = now
        self._ended = message.get("ended", False)
        if message.get("available") is False:
            self._unplayable.add(message["match_id"])
            self.director.healthy[message["match_id"]] = False
        elif message.get("available") is True:
            self._unplayable.discard(message["match_id"])
            self.director.healthy[message["match_id"]] = self._model_health[message["match_id"]]
        if self.playing:
            self._paused_at = None
        elif self._paused_at is None:
            self._paused_at = now
        if jumped:
            self.clock_epoch += 1
            self.director.reset(self.clock_epoch)
            self._last_recommendation = None
            partial_eof = (self._handle is not None and not self._finished
                           and any(value.get("status") in ("eof", "stopped")
                                   for value in self.worker_health.values()))
            if partial_eof:
                # An ended WebSocket shard cannot observe a new epoch. Restart
                # the whole owned group, including still-active sibling shards.
                self._stop_requested = True
                self._restart_after_seek = True
                self._worker_ready = False
                self._set_state("starting")
                self._publish_session()
            else:
                self._publish_session()
        elif previous_health != self.director.healthy:
            self._publish_session()
        return None

    def control(self, *, active=True):
        now = self.now()
        fresh = (self.last_report_at is not None
                 and self.monotonic() - self.last_report_at < self.config.heartbeat_seconds)
        result = {"session_id": self.session_id, "clock_epoch": self.clock_epoch,
                  "position": self.position, "playing": self.playing and fresh,
                  "rate": self.rate, "active": bool(active and fresh and self.controller is not None),
                  "expires_at": (now + max(0, self.config.heartbeat_seconds
                                             - (self.monotonic() - self.last_report_at))
                                 if fresh and active else now),
                  "updated_at": now}
        # Include the latest credentials until a worker actually observes them;
        # a one-shot update can be overwritten while it is busy assembling.
        result["sources"] = [source.worker_spec() for source in self.sources]
        return result

    def worker_spec(self):
        elapsed = (0 if self._monitor_started_at is None else
                   max(0, self.monotonic() - self._monitor_started_at))
        spec = {"session_id": self.session_id, "model_version": self.config.model_version,
                "mode": self.config.mode, "checkpoint": self.config.checkpoint,
                "clock_epoch": self.clock_epoch, "start_position": self.position,
                "matches": [source.worker_spec() for source in self.sources],
                "max_duration_seconds": max(5, self.config.max_duration_seconds - elapsed),
                "max_estimated_cost_usd": self.config.max_estimated_cost_usd - self._reserved_compute_usd}
        spec["gpu_workers"] = self.config.gpu_workers or math.ceil(len(self.sources) / MATCHES_PER_GPU)
        if self.config.mock_scores is not None:
            spec["mock_scores"] = dict(self.config.mock_scores)
        return spec

    async def _stop_worker(self):
        handle, self._handle = self._handle or self._stopping_handle, None
        self._worker_ready = False
        if handle is None:
            return
        self._stopping_handle = handle
        self.metrics["worker_stop_succeeded"] = False
        started = time.perf_counter()
        try:
            await asyncio.wait_for(self._control_rpc(self.control(active=False)), self.config.shutdown_rpc_seconds)
            self.metrics["shutdown_control_status"] = "completed"
        except TimeoutError:
            self.metrics["shutdown_control_status"] = "timeout"
            self.metrics["shutdown_sdk_thread_may_remain"] = True
            logger.warning("Inference shutdown control timed out; last viewer lease still expires")
        except Exception as exc:  # noqa: BLE001 - lease remains independent safety net
            self.metrics["shutdown_control_status"] = type(exc).__name__
            logger.warning("Inference control stop failed (%s)", type(exc).__name__)
        try:
            result = await asyncio.wait_for(asyncio.to_thread(self.bridge.stop, self.session_id, handle),
                                            self.config.shutdown_rpc_seconds)
            confirmed = (result.get("confirmed") is True if isinstance(result, dict) else
                         getattr(self.bridge, "transport", None) != "websocket")
            self.metrics["worker_stop_succeeded"] = confirmed
            self.metrics["shutdown_cancel_status"] = "completed" if confirmed else "unconfirmed"
            if isinstance(result, dict) and result.get("method") in ("websocket_graceful", "modal_input_cancel"):
                self.metrics["owned_stop_method"] = result["method"]
        except TimeoutError:
            self.metrics["shutdown_cancel_status"] = "timeout"
            self.metrics["shutdown_sdk_thread_may_remain"] = True
            logger.warning("Inference input cancellation timed out; cleanup is unconfirmed")
        except Exception as exc:  # noqa: BLE001
            self.metrics["shutdown_cancel_status"] = type(exc).__name__
            logger.warning("Inference input cancellation failed (%s)", type(exc).__name__)
        self.metrics["shutdown_worker_seconds"] = time.perf_counter() - started
        self._stopping_handle = None

    async def _control_rpc(self, control):
        started = time.perf_counter()
        try:
            return await asyncio.to_thread(self.bridge.update_control, self.session_id, control)
        finally:
            elapsed = time.perf_counter() - started
            self.metrics["control_rpc_count"] += 1
            self.metrics["control_rpc_seconds"] += elapsed
            self.metrics["control_rpc_last_seconds"] = elapsed

    async def _score_rpc(self):
        started = time.perf_counter()
        try:
            snapshot = await asyncio.to_thread(self.bridge.latest, self.session_id)
            completed = self.now()
            self.metrics["score_read_completed_at"] = completed
            if isinstance(snapshot, dict):
                produced = snapshot.get("produced_at")
                if isinstance(produced, (int, float)) and math.isfinite(produced):
                    self.metrics["score_age_at_read_seconds"] = max(0, completed - produced)
                ages = [max(0, completed - record["produced_at"]) for record in snapshot.get("scores", [])
                        if isinstance(record, dict) and isinstance(record.get("produced_at"), (int, float))
                        and math.isfinite(record["produced_at"])]
                if ages:
                    self.metrics["score_record_age_at_read_seconds"] = max(ages)
            return snapshot
        finally:
            elapsed = time.perf_counter() - started
            self.metrics["score_rpc_count"] += 1
            self.metrics["score_rpc_seconds"] += elapsed
            self.metrics["score_rpc_last_seconds"] = elapsed

    async def _start_worker(self):
        try:
            from ..ml_inference.replay_contract import MAX_WORKER_RATE
        except ImportError:
            from ml_inference.replay_contract import MAX_WORKER_RATE
        spec = self.worker_spec()
        # Reserve cold startup and idle overhead again for each attempted input,
        # so recovery cannot silently multiply the configured session allowance.
        estimate = (spec["max_duration_seconds"] + 330) * MAX_WORKER_RATE * spec["gpu_workers"]
        if estimate > spec["max_estimated_cost_usd"]:
            self._finished = True
            self._finished_reason = "session_budget_reached"
            self._set_state("stopped", self._finished_reason)
            return
        self._reserved_compute_usd += estimate
        self.metrics["reserved_compute_usd"] = self._reserved_compute_usd
        self._set_state("starting")
        await self._control_rpc(self.control())
        # Shield the submitted RPC: cancellation cannot stop a running thread.
        # Retaining its task lets shutdown recover and cancel the owned handle.
        self._start_inflight = asyncio.create_task(asyncio.to_thread(self.bridge.start, spec))
        self._handle = await asyncio.shield(self._start_inflight)
        self.metrics["worker_stop_succeeded"] = False
        self._start_inflight = None
        self._sources_changed = False
        if self._monitor_started_at is None:
            self._monitor_started_at = self.monotonic()

    async def _control_tick(self):
        now = self.monotonic()
        if self.registry.needs_refresh():
            try:
                self.sources = await asyncio.to_thread(self.registry.resolve)
                self._sources_changed = True
                self._publish_session()
            except Exception as exc:  # noqa: BLE001 - URL/credential errors stay private
                logger.warning("Media authorisation refresh failed (%s)", type(exc).__name__)
                self._set_state("degraded", "source_refresh_failed")
        if not self.config.monitor:
            return
        if (self._monitor_started_at is not None
                and now - self._monitor_started_at >= self.config.max_duration_seconds):
            self._finished = True
        fresh = self.last_report_at is not None and now - self.last_report_at < self.config.heartbeat_seconds
        paused_idle = (self._worker_ready and self._ready_at is not None
                       and now - self._ready_at > self.config.pause_idle_seconds
                       and self._paused_at is not None
                       and now - self._paused_at >= self.config.pause_idle_seconds)
        stop = self._stop_requested or self._finished or self._ended or not fresh or paused_idle
        if stop:
            had_worker = self._handle is not None
            await self._stop_worker()
            self._stop_requested = False
            if had_worker and not self._restart_after_seek:
                self.clock_epoch += 1
                self.director.reset(self.clock_epoch)
            self._restart_after_seek = False
            if self._finished:
                self._set_state("stopped", self._finished_reason)
            elif self._ended:
                self._set_state("ended")
            elif paused_idle:
                self._set_state("paused")
            elif not fresh:
                self._set_state("waiting")
            if not fresh or self._finished or self._ended or paused_idle:
                return
        if self._handle is None:
            if (self._monitor_started_at is not None
                    and self.config.max_duration_seconds - (now - self._monitor_started_at) < 5):
                self._finished = True
                self._set_state("stopped", "session_limit_reached")
                return
            if self.state == "paused" and not self.playing:
                return
            if self._restarts > self.config.max_restarts or now < self._retry_at:
                return
            await self._start_worker()
        else:
            await self._control_rpc(self.control())
            self._sources_changed = False
            if self._worker_ready and self._ready_at is not None and now - self._ready_at > 1:
                state = "running" if self.playing else "paused"
                if self.playing and not all(self.director.healthy.values()):
                    state = "degraded"
                self._set_state(state)

    async def _control_loop(self):
        while not self._closing:
            tick_started = self.monotonic()
            try:
                await self._control_tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - bounded recovery, secrets excluded
                self.metrics["worker_failures"] += 1
                self._restarts += 1
                self._retry_at = self.monotonic() + 5
                await self._stop_worker()
                self.clock_epoch += 1
                self.director.reset(self.clock_epoch)
                self._set_state("error", "inference_unavailable")
                logger.warning("Inference lifecycle failed (%s), recovery attempt %d",
                               type(exc).__name__, self._restarts)
            await asyncio.sleep(max(0, self.config.control_seconds - (self.monotonic() - tick_started)))

    def accept_snapshot(self, snapshot):
        """Also used by bounded real bridge-to-WebSocket validation."""
        if not isinstance(snapshot, dict):
            return False
        if self._finished or self._stop_requested or self._closing:
            return False
        identity = (snapshot.get("session_id") == self.session_id
                    and snapshot.get("model_version") == self.config.model_version
                    and snapshot.get("clock_epoch") == self.clock_epoch)
        if not identity:
            return False
        if (snapshot.get("score_kind") != ("model" if self.config.mode == "real" else "mock")
                or not isinstance(snapshot.get("worker_sequence"), int)
                or isinstance(snapshot.get("worker_sequence"), bool)
                or snapshot["worker_sequence"] <= self.director.last_worker_sequence):
            return False
        diagnostics = worker_diagnostics(snapshot)
        self.metrics["worker_last_state"] = diagnostics.pop("worker_state")
        self.metrics.update(diagnostics)
        health = snapshot.get("health", {})
        if isinstance(health, dict):
            self.worker_health = {match_id: {field: value.get(field) for field in
                ("status", "next_sample_index", "queue_samples")} for match_id, value in health.items()
                if match_id in self.director.records and isinstance(value, dict)}
            for match_id in self.director.match_ids:
                status = health.get(match_id)
                if isinstance(status, dict):
                    status = status.get("status")
                if status in ("healthy", "running", "ready"):
                    self._model_health[match_id] = True
                elif status in ("error", "failed", "unavailable", "eof", "stopped"):
                    self._model_health[match_id] = False
        if snapshot.get("state") == "error":
            self.director.last_worker_sequence = snapshot["worker_sequence"]
            self._last_recommendation = None
            self.director.reset_confirmation()
            self._stop_requested = True
            if transient_transport_error(snapshot):
                self._restarts += 1
                self._retry_at = self.monotonic() + 5
                self.metrics["worker_failures"] += 1
                self.metrics["transport_recoveries"] = self._restarts
                self._set_state("error", "inference_unavailable")
            else:
                self._finished = True
                self._finished_reason = "worker_error"
                self._set_state("error", "worker_error")
            return False
        if snapshot.get("state") == "stopped":
            self.director.last_worker_sequence = snapshot["worker_sequence"]
            self._last_recommendation = None
            self.director.reset_confirmation()
            reason = snapshot.get("reason")
            self._stop_requested = True
            if reason in ("session_limit", "all_sources_ended"):
                self._finished = True
                self._finished_reason = "all_sources_ended" if reason == "all_sources_ended" else "session_limit_reached"
                self._set_state("ended" if reason == "all_sources_ended" else "stopped", self._finished_reason)
            else:
                self._restarts += 1
                self._retry_at = self.monotonic() + 5
                self._set_state("error", "worker_lease_expired")
            return False
        if snapshot.get("state") in ("ready", "running") and not self._worker_ready:
            self._worker_ready = True
            self._ready_at = self.monotonic()
            self._set_state("running")
        started = time.perf_counter()
        previous_health = self.director.healthy.copy()
        changed = self.director.ingest(snapshot, now=self.now(), playback_position=self.position)
        for match_id in self.director.match_ids:
            self.director.healthy[match_id] = self._model_health[match_id] and match_id not in self._unplayable
        if previous_health != self.director.healthy:
            if (self._last_recommendation is not None
                    and not self.director.healthy.get(self._last_recommendation["selected_match_id"], False)):
                self._last_recommendation = None
            if (self.director.challenger_id is not None
                    and not self.director.healthy.get(self.director.challenger_id, False)):
                self.director.reset_confirmation()
            self._publish_session()
        previous_end = self.director.scores_observation_end
        emitted = self._evaluate_director() if changed or previous_health != self.director.healthy else False
        self.metrics["director_seconds"] = time.perf_counter() - started
        if not emitted and previous_end != self.director.scores_observation_end:
            self._publish_session()
        return emitted

    def _evaluate_director(self):
        if (self._finished or self._stop_requested or self._closing
                or self.state not in ("running", "degraded", "paused")):
            return False
        decision = self.director.decide(now=self.now(), playback_position=self.position, commit=False)
        if decision is None:
            return False
        self.metrics["recommendations"] += 1
        self._last_recommendation = {"type": "recommendation", "protocol_version": 1,
                                     "session_id": self.session_id, "sequence": self._next_sequence(),
                                     "model_version": self.config.model_version, "clock_epoch": self.clock_epoch,
                                     "score_kind": "model" if self.config.mode == "real" else "mock",
                                     "playback_time": self.position, "emitted_at": self.now(), **decision,
                                     "director": self.director.state(now=self.now(), playback_position=self.position)}
        self.publish(self._last_recommendation)
        return True

    async def _score_loop(self):
        while not self._closing:
            tick_started = self.monotonic()
            if self._handle is not None:
                try:
                    snapshot = await self._score_rpc()
                    self.accept_snapshot(snapshot)
                    # A cooldown can expire between inference ticks. Reuse only
                    # the still-fresh cohort; this never adds a confirmation.
                    self._evaluate_director()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    self._stop_requested = True
                    self._restarts += 1
                    self._retry_at = self.monotonic() + 5
                    self.metrics["worker_failures"] += 1
                    self._set_state("error", "score_transport_failed")
                    logger.warning("Inference score read failed (%s)", type(exc).__name__)
            await asyncio.sleep(max(0, self.config.poll_seconds - (self.monotonic() - tick_started)))

    def start(self):
        if not self._tasks:
            self._tasks = [asyncio.create_task(self._control_loop(), name="replay-control"),
                           asyncio.create_task(self._score_loop(), name="replay-scores")]

    async def close(self):
        if self._closed:
            return
        closing_started = time.perf_counter()
        self._closing = True
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        if self._start_inflight is not None:
            try:
                self._handle = await asyncio.wait_for(asyncio.shield(self._start_inflight), timeout=10)
            except TimeoutError:
                # The worker lease has expired. If SDK submission eventually
                # returns, cancel only that invocation; no extra polling task.
                def cancel_late(task):
                    if not task.cancelled() and task.exception() is None:
                        asyncio.create_task(asyncio.to_thread(self.bridge.stop, self.session_id, task.result()))
                self._start_inflight.add_done_callback(cancel_late)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Inference submission ended during shutdown (%s)", type(exc).__name__)
            self._start_inflight = None
        await self._stop_worker()
        self.playing = False
        self._set_state("stopped")
        self.metrics["shutdown_total_seconds"] = time.perf_counter() - closing_started
        self._closed = True
