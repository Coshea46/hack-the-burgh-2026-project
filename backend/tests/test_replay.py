"""Clock, director and real socket tests using an explicitly fake cloud bridge."""

import asyncio
import json
import threading
import time
from types import SimpleNamespace

import pytest
import websockets

from backend.main import AppController
from backend.replay import (
    Director,
    MatchSource,
    ReplaySession,
    SessionConfig,
    SourceRegistry,
)
from backend.websocket_manager import Connection, WebSocketManager, allowed_origins


class Clock:
    def __init__(self):
        self.value = 1000.0

    def __call__(self):
        return self.value


class FakeBridge:
    def __init__(self):
        self.calls = []
        self.snapshot = None
        self.error = None

    def start(self, spec):
        self.calls.append(("start", spec, threading.get_ident()))
        if self.error:
            raise self.error
        return "own-handle"

    def update_control(self, session_id, control):
        self.calls.append(("control", control, threading.get_ident()))

    def latest(self, session_id):
        self.calls.append(("latest", session_id, threading.get_ident()))
        return self.snapshot

    def stop(self, session_id, handle):
        self.calls.append(("stop", handle, threading.get_ident()))


def registry(count=2):
    return SourceRegistry([MatchSource(f"cam-{i}", f"Match {i}", offset_seconds=i * 10,
                                       key=f"match-{i}.mp4") for i in range(1, count + 1)])


def configuration(**kwargs):
    # These infrastructure fixtures use the immediate-confirmation mode. Mode
    # policy/default tests exercise Balanced independently below.
    kwargs.setdefault("director_mode", "all_action")
    return SessionConfig(monitor=True, mode="features_mock", model_version="mock-v1", **kwargs)


def scores(values=None, *, end=5, sequence=1, now=1000, epoch=0):
    values = values or {"cam-1": 0.4, "cam-2": 0.8}
    return {"session_id": "session", "model_version": "mock-v1", "clock_epoch": epoch,
            "worker_sequence": sequence, "score_kind": "mock", "state": "running",
            "health": {match_id: "healthy" for match_id in values},
            "scores": [{"match_id": match_id, "session_id": "session", "model_version": "mock-v1",
                        "clock_epoch": epoch, "sequence": sequence, "score": value,
                        "observation_start": end - 5, "observation_end": end,
                        "produced_at": now, "latency_seconds": 0.2, "status": "healthy"}
                       for match_id, value in values.items()]}


def director(**kwargs):
    kwargs.setdefault("staying_bonus", 0.10)
    kwargs.setdefault("minimum_switch_seconds", 2)
    kwargs.setdefault("confirmations_required", 1)
    return Director(["cam-1", "cam-2"], session_id="session", model_version="mock-v1",
                    mode="features_mock", **kwargs)


def playback(session, **kwargs):
    return {"type": "playback", "session_id": session.session_id,
            "match_id": session.director.current_match_id, "position": 0,
            "playing": True, "rate": 1, "stalled": False, **kwargs}


def test_default_registry_is_seven_public_encoded_media_sources():
    sources = SourceRegistry.from_env({}).resolve()
    assert len(sources) == 7
    assert sources[-1].worker_spec()["source_url"].endswith("/match-7.mp4")
    assert all(source.offset_seconds == 0 for source in sources)


def test_registry_presigns_refreshes_and_never_exposes_urls_in_repr():
    clock = Clock()

    class S3:
        def __init__(self):
            self.calls = []

        def generate_presigned_url(self, method, **kwargs):
            self.calls.append((method, kwargs))
            return f"https://example.com/media?signature=secret-{len(self.calls)}"

    s3 = S3()
    sources = SourceRegistry([MatchSource("cam-1", "Private", key="a b.mp4")],
                             access="presigned", url_ttl_seconds=120, s3_client=s3, now=clock)
    first = sources.resolve()[0]
    assert "secret" not in repr(first)
    assert first.playback_url == first.source_url
    assert s3.calls[0][1]["Params"]["Key"] == "a b.mp4"
    assert not sources.needs_refresh()
    clock.value += 61
    assert sources.needs_refresh()
    assert first.source_url != sources.resolve()[0].source_url


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, True, "3"])
def test_invalid_offsets_rejected(value):
    with pytest.raises(ValueError):
        MatchSource("cam-1", "Match", key="one", offset_seconds=value)


@pytest.mark.parametrize("source", ["file:///secret", "http://example.com/a", "https://user:pass@example.com/a"])
def test_invalid_source_protocols_rejected_without_echoing_source(source):
    with pytest.raises(ValueError) as error:
        MatchSource("cam-1", "Match", source_url=source)
    assert source not in str(error.value)


def test_source_configuration_offsets_and_bounded_registration():
    configured = SourceRegistry.from_env({"MATCHPULSE_MATCH_COUNT": "2",
                                          "MATCHPULSE_OFFSETS_JSON": '{"cam-2": 42.5}'}).resolve()
    assert configured[1].offset_seconds == 42.5
    with pytest.raises(ValueError, match="unique"):
        SourceRegistry([configured[0], configured[0]])
    with pytest.raises(ValueError):
        SourceRegistry.from_env({"MATCHPULSE_MATCH_COUNT": "8"})
    with pytest.raises(ValueError):
        SourceRegistry.from_env({"MATCHPULSE_OFFSETS_JSON": '{"unknown":1}'})


def test_monitoring_is_disabled_unless_server_environment_explicitly_enables_it():
    assert not SessionConfig.from_env({"MATCHPULSE_ML_MODE": "real"}).monitor
    with pytest.raises(ValueError, match="explicit"):
        SessionConfig.from_env({"MATCHPULSE_MONITOR": "true"})
    with pytest.raises(ValueError, match="CHECKPOINT"):
        SessionConfig.from_env({"MATCHPULSE_MONITOR": "true", "MATCHPULSE_ML_MODE": "real"})
    with pytest.raises(ValueError):
        SessionConfig.from_env({"MATCHPULSE_MONITOR": "true", "MATCHPULSE_ML_MODE": "mock"})


def test_transport_defaults_to_private_websocket_without_importing_it_when_disabled(monkeypatch):
    import sys

    calls = []

    class WebSocketClient:
        @classmethod
        def from_env(cls):
            calls.append("private_ws")
            return FakeBridge()

    monkeypatch.setitem(sys.modules, "backend.ml_inference.replay_ws_client",
                        SimpleNamespace(ReplayWebSocketClient=WebSocketClient))

    async def scenario():
        disabled = await ReplaySession(registry(), config=SessionConfig.from_env({})).initialize()
        assert disabled.config.replay_transport == "websocket" and not calls
        await disabled.close()
        config = SessionConfig.from_env({"MATCHPULSE_MONITOR": "true", "MATCHPULSE_ML_MODE": "features_mock",
                                         "MATCHPULSE_MODAL_WS_URL": "https://private.modal.run/session",
                                         "MATCHPULSE_MODAL_WS_TOKEN": "private-super-secret-token"})
        session = await ReplaySession(registry(), config=config).initialize()
        session.connect("viewer")
        assert calls == ["private_ws"]
        public = json.dumps({"session": session.snapshot(), "metrics": session.metrics})
        assert "private.modal.run" not in public and "private-super-secret-token" not in public
        assert session.metrics["replay_transport"] == "websocket"
        await session.close()

    asyncio.run(scenario())
    assert SessionConfig.from_env({"MATCHPULSE_REPLAY_TRANSPORT": "dict"}).replay_transport == "dict"
    with pytest.raises(ValueError, match="REPLAY_TRANSPORT"):
        SessionConfig.from_env({"MATCHPULSE_REPLAY_TRANSPORT": "unknown"})


@pytest.mark.parametrize("result,confirmed", [(None, False), ({"confirmed": False}, False),
                                             ({"confirmed": True, "method": "websocket_graceful"}, True)])
def test_websocket_stop_confirmation_distinguishes_acknowledgement_from_socket_close(result, confirmed):
    async def scenario():
        class SocketBridge(FakeBridge):
            transport = "websocket"

            def stop(self, session_id, handle):
                return result

        session = await ReplaySession(registry(), config=configuration(), bridge=SocketBridge()).initialize()
        session._handle = "owned-socket-session"
        await session.close()
        assert session.metrics["worker_stop_succeeded"] is confirmed
        assert session.metrics["owned_stop_method"] == "websocket_graceful"
        assert session.metrics["shutdown_cancel_status"] == ("completed" if confirmed else "unconfirmed")

    asyncio.run(scenario())


def test_mock_scores_require_explicit_mock_mode_and_registered_matches():
    config = SessionConfig.from_env({"MATCHPULSE_MONITOR": "true", "MATCHPULSE_ML_MODE": "features_mock",
                                     "MATCHPULSE_MOCK_SCORES_JSON": '{"cam-1":0.1,"cam-2":0.9}'})
    assert config.mock_scores == {"cam-1": 0.1, "cam-2": 0.9}
    with pytest.raises(ValueError, match="features_mock"):
        SessionConfig(monitor=True, mode="real", checkpoint="v1/classifier.pt", mock_scores={"cam-1": 0.8})

    async def scenario():
        session = await ReplaySession(registry(), config=config, bridge=FakeBridge()).initialize()
        assert session.worker_spec()["mock_scores"]["cam-2"] == 0.9
        await session.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("mode,checkpoint", [("features_mock", None), ("real", "v1/classifier.pt")])
def test_backend_worker_spec_and_clock_validate_against_real_bridge_contract(mode, checkpoint):
    from backend.ml_inference.replay_contract import validate_control, validate_session

    async def scenario():
        config = SessionConfig(monitor=True, mode=mode, checkpoint=checkpoint,
                               model_version=checkpoint or "features-mock-v1")
        session = await ReplaySession(registry(), config=config, bridge=FakeBridge()).initialize()
        session.connect("viewer")
        session.receive("viewer", playback(session, playing=False))
        assert validate_session(session.worker_spec())
        assert validate_control(session.session_id, session.control())
        await session.close()

    asyncio.run(scenario())


def test_gpu_shards_default_by_source_count_and_share_one_budget():
    async def scenario():
        session = await ReplaySession(registry(7), config=configuration(), bridge=FakeBridge()).initialize()
        from backend.ml_inference.replay_contract import MATCHES_PER_GPU

        assert session.worker_spec()["gpu_workers"] == (7 + MATCHES_PER_GPU - 1) // MATCHES_PER_GPU
        await session.close()
        session = await ReplaySession(registry(7), config=configuration(gpu_workers=1),
                                       bridge=FakeBridge()).initialize()
        assert session.worker_spec()["gpu_workers"] == 1
        await session.close()
        bridge = FakeBridge()
        session = await ReplaySession(registry(7), config=configuration(max_estimated_cost_usd=0.2),
                                       bridge=bridge).initialize()
        session.connect("viewer")
        session.receive("viewer", playback(session))
        await session._control_tick()
        assert session.error_code == "session_budget_reached"
        assert not bridge.calls
        await session.close()

    asyncio.run(scenario())
    assert SessionConfig.from_env({"MATCHPULSE_GPU_WORKERS": ""}).gpu_workers is None
    with pytest.raises(ValueError):
        configuration(gpu_workers=5)


def test_four_worker_allocation_reserves_every_resource_against_one_allowance():
    from backend.ml_inference.replay_contract import MAX_WORKER_RATE, validate_session

    async def scenario():
        clock, bridge = Clock(), FakeBridge()
        session = await ReplaySession(registry(7), config=configuration(max_estimated_cost_usd=2),
                                       bridge=bridge, now=clock, monotonic=clock).initialize()
        session.connect("viewer")
        session.receive("viewer", playback(session))
        await session._control_tick()
        spec = next(call[1] for call in bridge.calls if call[0] == "start")
        assert spec["gpu_workers"] == 4 and len(spec["matches"]) == 7
        assert validate_session(spec)
        assert session.metrics["reserved_compute_usd"] == pytest.approx((300 + 330) * MAX_WORKER_RATE * 4)
        assert session.worker_spec()["max_estimated_cost_usd"] == pytest.approx(
            2 - session.metrics["reserved_compute_usd"])
        await session.close()
        assert session.metrics["worker_stop_succeeded"]

    asyncio.run(scenario())


def test_control_and_score_rpc_cadence_subtracts_network_time_without_overlapping_calls():
    class SlowBridge(FakeBridge):
        def __init__(self):
            super().__init__()
            self.starts = {"control": [], "score": []}
            self.active = {"control": 0, "score": 0}
            self.overlapped = False

        def rpc(self, kind, duration):
            self.starts[kind].append(time.perf_counter())
            self.active[kind] += 1
            self.overlapped |= self.active[kind] > 1
            time.sleep(duration)
            self.active[kind] -= 1

        def update_control(self, session_id, control):
            self.rpc("control", 0.08)

        def latest(self, session_id):
            self.rpc("score", 0.04)
            return {"produced_at": time.time() - 0.1, "scores": []}

    async def scenario():
        bridge = SlowBridge()
        session = await ReplaySession(registry(), config=configuration(control_seconds=0.12, poll_seconds=0.06),
                                       bridge=bridge).initialize()
        session.connect("viewer")
        session.receive("viewer", playback(session))
        session._handle = "already-started"
        session.start()
        for _ in range(200):
            if len(bridge.starts["control"]) >= 5 and len(bridge.starts["score"]) >= 8:
                break
            await asyncio.sleep(0.01)
        # Gracefully finish the final in-flight reads/writes before teardown.
        session._closing = True
        await asyncio.gather(*session._tasks)
        for kind, ceiling in (("control", 0.17), ("score", 0.09)):
            starts = bridge.starts[kind]
            assert len(starts) >= 5
            average_interval = (starts[-1] - starts[0]) / (len(starts) - 1)
            assert average_interval < ceiling
        assert not bridge.overlapped
        assert session.metrics["control_rpc_count"] >= 5
        assert session.metrics["score_rpc_count"] >= 8
        assert session.metrics["control_rpc_seconds"] >= 5 * 0.08
        assert session.metrics["score_rpc_seconds"] >= 8 * 0.04
        assert session.metrics["score_age_at_read_seconds"] >= 0.1
        assert session.metrics["score_read_completed_at"] > 0
        await session.close()

    asyncio.run(scenario())


def test_failed_playback_publishes_health_and_allows_valid_scored_fallback_during_hold():
    async def scenario():
        clock = Clock()
        sent = []
        session = await ReplaySession(registry(), config=configuration(), bridge=FakeBridge(),
                                       publish=sent.append, now=clock, monotonic=clock,
                                       session_id="session").initialize()
        session.connect("viewer")
        session.director.manual_select("cam-1", now=clock.value)
        session.director.auto_enabled = False
        session.receive("viewer", playback(session, position=5, available=False))
        assert sent[-1]["type"] == "session"
        assert not sent[-1]["matches"][0]["healthy"]
        assert not session.accept_snapshot(scores())
        assert session.director.current_match_id == "cam-1"
        assert sent[-1]["director"]["latest_scores"] == {"cam-2": 0.8}
        session.director.manual_hold_until = 0  # Fallback is evaluated after the user's hold.
        session.receive("viewer", {"type": "auto", "session_id": "session", "enabled": True})
        assert session._evaluate_director()
        assert sent[-1]["selected_match_id"] == "cam-2"
        assert "cam-1" not in sent[-1]["scores"]
        await session.close()

    asyncio.run(scenario())


def test_paid_probe_refuses_cloud_without_explicit_backend_monitor(monkeypatch):
    from backend import probe_replay

    monkeypatch.setenv("MATCHPULSE_MONITOR", "false")
    monkeypatch.setattr("sys.argv", ["probe_replay", "--allow-cloud"])
    with pytest.raises(SystemExit) as result:
        probe_replay.main()
    assert result.value.code == 2


def test_probe_accounts_for_final_window_censoring_and_complete_drain():
    from backend.probe_replay import delivery_summary

    records = [{"observation_end": end} for end in range(5, 19, 2)]
    original = delivery_summary(records, 20, 20.75)
    assert original["expected_endpoints"] == list(range(5, 20, 2))
    assert original["missing_endpoints"] == [19]
    assert original["censored_endpoints"] == [19]
    assert original["missing_after_drain"] == []
    assert not original["complete"]
    drained = delivery_summary(records, 20, 23.25)
    assert drained["censored_endpoints"] == []
    assert drained["missing_after_drain"] == [19]
    assert drained["undelivered_past_3s"] == [19]
    records.append({"observation_end": 19})
    complete = delivery_summary(records, 20, 23.25)
    assert complete["complete"] and complete["cadence_order_valid"] and complete["drain_complete"]
    assert complete["cadence_seconds"] == [2] * 7


def test_probe_detects_missing_order_duplicates_and_reported_backlog():
    from backend.probe_replay import delivery_summary, reported_backlog

    results = delivery_summary([{"observation_end": end} for end in [5, 9, 7, 7]], 11, 14.25)
    assert not results["cadence_order_valid"]
    assert not results["complete"]
    assert results["duplicate_endpoints"] == [7]
    assert results["missing_after_drain"] == [11]
    lag = reported_backlog({"cam-1": {"next_sample_index": 270, "queue_samples": 16},
                            "cam-2": {"next_sample_index": 300, "queue_samples": 0}}, 20)
    assert lag["maximum_backlog_seconds"] == 2
    assert lag["maximum_queue_samples"] == 16
    assert lag["streams"]["cam-2"]["backlog_samples"] == 0


def test_probe_capacity_rejects_degraded_cohort_even_with_complete_delivered_cadence():
    from backend.probe_replay import capacity_result, delivery_summary

    registered = {"cam-1", "cam-2", "cam-3"}
    records = [{"observation_end": end, "scores": dict.fromkeys(registered, 0.5)} for end in (5, 7, 9)]
    cadence = delivery_summary(records, 10, 13.25)
    assert cadence["complete"]
    assert capacity_result(records, registered, cadence_complete=True, errors=[])["passed"]
    records[1]["scores"].pop("cam-3")
    result = capacity_result(records, registered, cadence_complete=cadence["complete"], errors=[])
    assert not result["passed"] and not result["full_source_cohort_complete"]
    assert result["full_source_cohort_count"] == 2 and result["degraded_recommendation_count"] == 1
    assert result["registered_source_count"] == 3
    assert result["recommendation_count"] == 3  # It remains a valid degraded application recommendation.


def test_origin_allowlist_defaults_and_explicit_production_configuration(monkeypatch):
    monkeypatch.delenv("MATCHPULSE_ALLOWED_ORIGINS", raising=False)
    assert allowed_origins() == [None, "http://localhost:3000", "http://127.0.0.1:3000"]
    monkeypatch.setenv("MATCHPULSE_ALLOWED_ORIGINS", "https://matchpulse.example, https://preview.example/")
    assert allowed_origins() == [None, "https://matchpulse.example", "https://preview.example"]
    for origin in ["*", "https://user:password@example.com", "https://example.com/path", "https://example.com:bad"]:
        with pytest.raises(ValueError, match="MATCHPULSE_ALLOWED_ORIGINS"):
            allowed_origins(origin)


def test_websocket_handshake_rejects_cross_site_origin_before_exposing_media_urls():
    async def scenario():
        session = await ReplaySession(registry()).initialize()
        manager = WebSocketManager(session, host="127.0.0.1", port=0, origins="https://matchpulse.example")
        await manager.start()
        url = f"ws://127.0.0.1:{manager.server.sockets[0].getsockname()[1]}"
        try:
            with pytest.raises(websockets.InvalidStatusCode) as error:
                async with websockets.connect(url, origin="https://other.example"):
                    raise AssertionError("Cross-site origin reached handler")
            assert error.value.status_code == 403
            assert not manager.clients and not session.clients
            async with websockets.connect(url, origin="https://matchpulse.example") as socket:
                assert json.loads(await socket.recv())["type"] == "session"
            async with websockets.connect(url) as socket:
                assert json.loads(await socket.recv())["type"] == "session"
        finally:
            await manager.close()
            await session.close()

    asyncio.run(scenario())


def test_director_stay_bonus_raw_scores_and_deterministic_ties():
    d = director()
    assert d.ingest(scores({"cam-1": 0.4, "cam-2": 0.5}), now=1000, playback_position=5)
    first = d.decide(now=1000, playback_position=5)
    assert first["selected_match_id"] == "cam-1"
    assert first["scores"]["cam-1"] == 0.4
    assert d.ingest(scores({"cam-1": 0.4, "cam-2": 0.55}, end=7, sequence=2),
                    now=1000, playback_position=7)
    assert d.decide(now=1000, playback_position=7)["selected_match_id"] == "cam-2"
    # The bonus is applied once to comparison; stored scores remain unmodified.
    assert d.records["cam-1"][-1].value == 0.4


def test_director_reports_post_compute_delivery_separately_from_worker_compute():
    d = director()
    assert d.ingest(scores(now=999.5), now=1000, playback_position=5)
    decision = d.decide(now=1000, playback_position=5)
    assert decision["worker_completion_to_backend_seconds"] == 0.5
    assert decision["latency_seconds"] == pytest.approx(0.7)


def test_director_switch_interval_manual_hold_and_auto_disable():
    d = director()
    d.ingest(scores(), now=1000, playback_position=5)
    assert d.decide(now=1000, playback_position=5)["selected_match_id"] == "cam-2"
    d.ingest(scores({"cam-1": 1, "cam-2": 0}, end=7, sequence=2, now=1001),
             now=1001, playback_position=7)
    assert d.decide(now=1001, playback_position=7)["selected_match_id"] == "cam-2"
    d.manual_select("cam-1", now=1002)
    d.ingest(scores(end=9, sequence=3, now=1003), now=1003, playback_position=9)
    assert d.decide(now=1003, playback_position=9)["selected_match_id"] == "cam-1"
    d.auto_enabled = False
    d.ingest(scores(end=11, sequence=4, now=1033), now=1033, playback_position=11)
    assert d.decide(now=1033, playback_position=11)["selected_match_id"] == "cam-1"
    d.auto_enabled = True
    d.ingest(scores(end=13, sequence=5, now=1035), now=1035, playback_position=13)
    assert d.decide(now=1035, playback_position=13)["selected_match_id"] == "cam-2"


@pytest.mark.parametrize("field,value", [("score", float("nan")), ("score", -0.1), ("score", 1.1),
                                        ("sequence", True), ("match_id", "unknown"),
                                        ("session_id", "previous-session"), ("model_version", "old"),
                                        ("observation_start", 1), ("produced_at", 990),
                                        ("produced_at", 1002), ("latency_seconds", 4),
                                        ("clock_epoch", 1)])
def test_invalid_records_never_trigger_incomplete_cohort_switch(field, value):
    d = director()
    snapshot = scores()
    snapshot["scores"][1][field] = value
    d.ingest(snapshot, now=1000, playback_position=5)
    assert d.decide(now=1000, playback_position=5) is None
    assert d.current_match_id == "cam-1"


@pytest.mark.parametrize("field,value", [("session_id", "old"), ("model_version", "old"),
                                        ("worker_sequence", -1), ("worker_sequence", True),
                                        ("clock_epoch", 1), ("score_kind", "model")])
def test_old_or_wrong_snapshot_rejected(field, value):
    d = director()
    snapshot = scores()
    snapshot[field] = value
    assert not d.ingest(snapshot, now=1000, playback_position=5)


def test_future_stale_out_of_order_and_repeated_windows_rejected():
    d = director()
    assert not d.ingest(scores(), now=1000, playback_position=4.9)
    d = director()
    assert not d.ingest(scores(), now=1000, playback_position=9)
    d = director()
    assert d.ingest(scores(), now=1000, playback_position=5)
    assert not d.ingest(scores(), now=1000, playback_position=5)
    out_of_order = scores(sequence=2)
    assert not d.ingest(out_of_order, now=1000, playback_position=5)
    assert d.decide(now=1000, playback_position=5)
    assert d.decide(now=1000, playback_position=5) is None


def test_partial_cohort_waits_and_unavailable_stream_is_excluded():
    d = director()
    assert d.ingest(scores({"cam-1": 0.2}), now=1000, playback_position=5)
    assert d.decide(now=1000, playback_position=5) is None
    snapshot = scores({"cam-2": 0.9}, sequence=2)
    d.ingest(snapshot, now=1000, playback_position=5)
    assert d.decide(now=1000, playback_position=5)["selected_match_id"] == "cam-2"
    snapshot = scores({"cam-1": 0.6}, end=7, sequence=3)
    snapshot["health"]["cam-2"] = {"status": "eof"}
    d.ingest(snapshot, now=1002, playback_position=7)
    assert d.decide(now=1002, playback_position=7)["selected_match_id"] == "cam-1"


def test_cache_is_bounded_and_seek_clears_previous_epoch():
    d = director()
    for sequence in range(1, 20):
        end = 3 + sequence * 2
        d.ingest(scores(end=end, sequence=sequence), now=1000, playback_position=end)
    assert all(len(records) == 2 for records in d.records.values())
    d.reset(1)
    assert not any(d.records.values())
    assert not d.ingest(scores(), now=1000, playback_position=5)
    assert d.ingest(scores(epoch=1), now=1000, playback_position=5)


def test_session_clock_manual_selection_roles_and_no_extrapolation():
    async def scenario():
        clock = Clock()
        bridge = FakeBridge()
        session = await ReplaySession(registry(), config=configuration(), bridge=bridge,
                                       now=clock, monotonic=clock, session_id="session").initialize()
        assert session.connect("first")["controls_enabled"]
        assert not session.connect("second")["controls_enabled"]
        assert session.receive("second", playback(session))["code"] == "viewer_in_use"
        assert session.receive("first", playback(session, position=10)) is None
        clock.value += 2
        assert session.control()["position"] == 10
        assert session.control()["expires_at"] == clock.value + 3
        assert not bridge.calls  # A frontend report doesn't make an SDK call.
        assert session.receive("first", {"type": "select", "session_id": "session",
                                          "match_id": "cam-2"}) is None
        assert session.director.current_match_id == "cam-2"
        assert session.director.manual_hold_until == clock.value + 30
        assert session.receive("first", playback(session, position=1)) is None
        assert session.clock_epoch == 1
        session.disconnect("first")
        assert session.controls_enabled("second")
        assert not session.control()["active"]
        await session.close()

    asyncio.run(scenario())


def test_session_start_ready_scores_shutdown_and_sdk_calls_off_event_loop():
    async def scenario():
        clock = Clock()
        bridge = FakeBridge()
        sent = []
        session = await ReplaySession(registry(), config=configuration(), bridge=bridge,
                                       publish=sent.append, now=clock, monotonic=clock,
                                       session_id="session").initialize()
        session.connect("viewer")
        # Startup buffer reports paused at zero and still starts the worker.
        session.receive("viewer", playback(session, playing=False))
        await session._control_tick()
        assert session.state == "starting"
        assert [call[0] for call in bridge.calls] == ["control", "start"]
        assert bridge.calls[0][1]["position"] == 0
        assert bridge.calls[1][1]["matches"][1]["offset_seconds"] == 20
        ready = scores()
        ready.update(state="ready", scores=[])
        assert not session.accept_snapshot(ready)
        assert session.state == "running"
        session.receive("viewer", playback(session, position=5))
        # Five seconds later is normal motion rather than an instantaneous seek.
        session.clock_epoch = 0
        session.director.reset(0)
        assert session.accept_snapshot(scores(sequence=2))
        rec = sent[-1]
        assert rec["type"] == "recommendation" and rec["selected_match_id"] == "cam-2"
        assert rec["score_kind"] == "mock" and rec["valid_until"] == 1003
        # A published proposal isn't committed until the actual viewer accepts.
        assert session.director.current_match_id == "cam-1"
        assert session.receive("viewer", playback(session, match_id="cam-1", position=5)) is None
        assert session.receive("viewer", {"type": "ack", "session_id": "session",
                                          "sequence": rec["sequence"], "clock_epoch": 0,
                                          "match_id": "cam-2"}) is None
        assert session.director.current_match_id == "cam-2"
        assert session.metrics["last_ack"]["observation_to_ack_seconds"] == 0.2
        await session.close()
        assert [call[0] for call in bridge.calls][-2:] == ["control", "stop"]
        assert not bridge.calls[-2][1]["active"]
        assert all(call[2] != threading.get_ident() for call in bridge.calls)

    asyncio.run(scenario())


def test_heartbeat_expiration_pause_idle_eof_and_duration_cleanup():
    async def scenario():
        clock = Clock()
        bridge = FakeBridge()
        session = await ReplaySession(registry(), config=configuration(max_duration_seconds=10),
                                       bridge=bridge, now=clock, monotonic=clock).initialize()
        session.connect("viewer")
        session.receive("viewer", playback(session))
        await session._control_tick()
        clock.value += 6
        await session._control_tick()
        assert session._handle is None and session.state == "waiting"
        assert any(call[0] == "stop" for call in bridge.calls)
        clock.value += 5
        session.receive("viewer", playback(session, ended=True))
        await session._control_tick()
        assert session.state == "stopped" and session._finished
        await session.close()

    asyncio.run(scenario())


def test_worker_start_failure_has_bounded_retries():
    async def scenario():
        clock = Clock()
        bridge = FakeBridge()
        bridge.error = RuntimeError("do-not-log-a-secret-URL")
        session = await ReplaySession(registry(), config=configuration(max_restarts=1), bridge=bridge,
                                       now=clock, monotonic=clock).initialize()
        session.connect("viewer")
        session.receive("viewer", playback(session))
        # Exercise the background handler that records failures and retry delay.
        session.start()
        await asyncio.sleep(0.1)
        assert session.state == "error"
        assert session._restarts == 1
        assert session.snapshot()["error_code"] == "inference_unavailable"
        await session.close()

    asyncio.run(scenario())


def test_pending_socket_messages_keep_only_latest_per_type():
    async def scenario():
        session = await ReplaySession(registry()).initialize()
        manager = WebSocketManager(session)
        connection = Connection(None)
        for sequence in range(1000):
            manager._queue("one", connection, {"type": "recommendation", "sequence": sequence})
        assert len(connection.pending) == 1
        assert connection.pending["recommendation"]["sequence"] == 999
        await session.close()

    asyncio.run(scenario())


def test_real_websocket_session_manual_auto_recommendation_and_reconnect():
    async def receive_kind(socket, kind):
        for _ in range(10):
            message = json.loads(await asyncio.wait_for(socket.recv(), 2))
            if message["type"] == kind:
                return message
        raise AssertionError(f"Missing message {kind}")

    async def scenario():
        bridge = FakeBridge()
        clock = Clock()
        session = await ReplaySession(registry(), config=configuration(), bridge=bridge,
                                       now=clock, monotonic=clock, session_id="session").initialize()
        manager = WebSocketManager(session, host="127.0.0.1", port=0)
        await manager.start()
        port = manager.server.sockets[0].getsockname()[1]
        try:
            async with websockets.connect(f"ws://127.0.0.1:{port}") as socket:
                initial = await receive_kind(socket, "session")
                assert initial["controls_enabled"] and len(initial["matches"]) == 2
                await socket.send(json.dumps(playback(session, position=5)))
                await asyncio.sleep(0.02)
                assert session.position == 5
                assert session.accept_snapshot(scores())
                recommendation = await receive_kind(socket, "recommendation")
                assert recommendation["selected_match_id"] == "cam-2"
                assert recommendation["sequence"] > initial["sequence"]
                await socket.send(json.dumps({"type": "select", "session_id": "session", "match_id": "cam-1"}))
                selected = await receive_kind(socket, "session")
                assert selected["current_match_id"] == "cam-1"
                await socket.send(json.dumps({"type": "auto", "session_id": "session", "enabled": False}))
                assert not (await receive_kind(socket, "session"))["auto_enabled"]
                await socket.send("not-json")
                assert (await receive_kind(socket, "error"))["code"] == "invalid_json"
            async with websockets.connect(f"ws://127.0.0.1:{port}") as socket:
                restored = await receive_kind(socket, "session")
                assert restored["playback"]["position"] == 5
                assert restored["current_match_id"] == "cam-1"
                assert not restored["auto_enabled"]
            assert not bridge.calls  # Socket handlers never call Modal.
        finally:
            await manager.close()
            await session.close()

    asyncio.run(scenario())


def test_app_default_startup_has_no_legacy_rgb_ingester():
    controller = AppController(registry=registry(), config=SessionConfig(), host="127.0.0.1", port=0)
    assert not hasattr(controller, "ingester")
    assert not controller.session.config.monitor


def test_discarded_proposal_keeps_actual_viewer_clock_and_late_ack_cannot_undo_manual_pick():
    async def scenario():
        clock = Clock()
        sent = []
        session = await ReplaySession(registry(), config=configuration(), bridge=FakeBridge(),
                                       publish=sent.append, now=clock, monotonic=clock,
                                       session_id="session").initialize()
        session.connect("viewer")
        session.receive("viewer", playback(session, position=5))
        assert session.accept_snapshot(scores())
        proposal = sent[-1]
        assert proposal["selected_match_id"] == "cam-2"
        assert session.receive("viewer", playback(session, match_id="cam-1", position=5)) is None
        assert session.director.current_match_id == "cam-1"
        session.receive("viewer", {"type": "select", "session_id": "session", "match_id": "cam-1"})
        error = session.receive("viewer", {"type": "ack", "session_id": "session",
                                            "sequence": proposal["sequence"], "clock_epoch": 0,
                                            "match_id": "cam-2"})
        assert error["code"] == "stale_ack"
        assert session.director.current_match_id == "cam-1"
        await session.close()

    asyncio.run(scenario())


def test_startup_hold_does_not_trigger_idle_gpu_shutdown_and_pause_later_does():
    async def scenario():
        clock = Clock()
        bridge = FakeBridge()
        session = await ReplaySession(registry(), config=configuration(), bridge=bridge,
                                       now=clock, monotonic=clock, session_id="session").initialize()
        session.connect("viewer")
        session.receive("viewer", playback(session, playing=False))
        await session._control_tick()
        clock.value += 20
        session.receive("viewer", playback(session, playing=False))
        await session._control_tick()
        assert session._handle == "own-handle" and session.state == "starting"
        ready = scores(now=clock.value)
        ready.update(state="ready", scores=[])
        session.accept_snapshot(ready)
        clock.value += 11
        session.receive("viewer", playback(session, playing=False))
        await session._control_tick()
        assert session._handle is None and session.state == "paused"
        # Fresh pause heartbeats don't create another GPU input.
        await session._control_tick()
        assert len([call for call in bridge.calls if call[0] == "start"]) == 1
        session.receive("viewer", playback(session, playing=True))
        await session._control_tick()
        assert len([call for call in bridge.calls if call[0] == "start"]) == 2
        await session.close()

    asyncio.run(scenario())


def test_shutdown_during_slow_submission_recovers_and_cancels_owned_handle():
    async def scenario():
        gate = threading.Event()

        class SlowBridge(FakeBridge):
            def start(self, spec):
                gate.wait(2)
                return super().start(spec)

        bridge = SlowBridge()
        session = await ReplaySession(registry(), config=configuration(), bridge=bridge).initialize()
        session.connect("viewer")
        session.receive("viewer", playback(session))
        session.start()
        for _ in range(100):
            if session._start_inflight is not None:
                break
            await asyncio.sleep(0.001)
        closing = asyncio.create_task(session.close())
        await asyncio.sleep(0.01)
        gate.set()
        await closing
        assert session._handle is None
        assert any(call[0] == "stop" and call[1] == "own-handle" for call in bridge.calls)

    asyncio.run(scenario())


def test_shutdown_bounds_blocked_rpc_and_reports_unconfirmed_cancellation():
    async def scenario():
        release = threading.Event()

        class SlowStop(FakeBridge):
            def stop(self, session_id, handle):
                release.wait(2)

        session = await ReplaySession(registry(), config=configuration(shutdown_rpc_seconds=0.02),
                                       bridge=SlowStop()).initialize()
        session.connect("viewer")
        session.receive("viewer", playback(session))
        session._handle = "owned-handle"
        before = time.perf_counter()
        try:
            await session.close()
            assert time.perf_counter() - before < 0.5
            assert session.metrics["shutdown_cancel_status"] == "timeout"
            assert not session.metrics["worker_stop_succeeded"]
            assert session.metrics["shutdown_sdk_thread_may_remain"]
            elapsed = session.metrics["shutdown_total_seconds"]
            await session.close()  # Idempotent and preserves the actual teardown timings.
            assert session.metrics["shutdown_total_seconds"] == elapsed
        finally:
            release.set()

    asyncio.run(scenario())


def test_restart_cost_reservations_enforce_whole_session_budget():
    async def scenario():
        bridge = FakeBridge()
        clock = Clock()
        session = await ReplaySession(registry(), config=configuration(max_estimated_cost_usd=0.2),
                                       bridge=bridge, now=clock, monotonic=clock).initialize()
        session.connect("viewer")
        session.receive("viewer", playback(session))
        await session._control_tick()
        assert session._handle is not None
        from backend.ml_inference.replay_contract import MAX_WORKER_RATE

        assert session.metrics["reserved_compute_usd"] == pytest.approx((300 + 330) * MAX_WORKER_RATE)
        session._stop_requested = True
        await session._control_tick()
        assert session._handle is None and session._finished
        assert session.error_code == "session_budget_reached"
        assert len([call for call in bridge.calls if call[0] == "start"]) == 1
        await session.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("reason", ["session_limit", "all_sources_ended"])
def test_terminal_worker_snapshot_stops_instead_of_spawning_forever(reason):
    async def scenario():
        bridge = FakeBridge()
        session = await ReplaySession(registry(), config=configuration(), bridge=bridge,
                                       session_id="session").initialize()
        session.connect("viewer")
        session.receive("viewer", playback(session))
        await session._control_tick()
        terminal = scores(now=time.time())
        terminal.update(state="stopped", reason=reason, scores=[])
        assert not session.accept_snapshot(terminal)
        await session._control_tick()
        assert session._finished and session._handle is None
        await session._control_tick()
        assert len([call for call in bridge.calls if call[0] == "start"]) == 1
        await session.close()

    asyncio.run(scenario())


def test_worker_startup_diagnostics_survive_error_handling_without_source_or_exception_text():
    from backend.replay.session import worker_diagnostics

    async def scenario():
        session = await ReplaySession(registry(), config=configuration(), bridge=FakeBridge(),
                                       session_id="session").initialize()
        snapshot = scores()
        snapshot.update(state="error", reason="shard_error", error_type="ValueError",
                        error_phase="checkpoint", error="https://private.example/?token=secret",
                        shard_errors={"0": {"state": "error", "reason": "checkpoint_unavailable",
                                            "error_type": "ValueError", "error_phase": "checkpoint",
                                            "message": "private secret exception text"},
                                      "1": {"state": "error", "reason": "https://secret.example",
                                            "error_type": "ValueError: token=secret",
                                            "error_phase": ["secret"]}, "other-secret-shard": {}})
        assert not session.accept_snapshot(snapshot)
        assert session.metrics["worker_last_state"] == "error"
        assert session.metrics["worker_reason"] == "shard_error"
        assert session.metrics["worker_error_type"] == "ValueError"
        assert session.metrics["worker_shard_errors"]["0"]["reason"] == "checkpoint_unavailable"
        assert session.metrics["worker_shard_errors"]["1"]["reason"] is None
        assert "secret" not in json.dumps(session.metrics)
        assert "message" not in json.dumps(worker_diagnostics(snapshot))
        assert len(session.metrics["worker_shard_errors"]) == 2
        await session.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("match_count,workers", [(2, 1), (7, 2), (7, 4)])
def test_transport_loss_recovers_once_with_new_epoch_and_shared_reserved_budget(match_count, workers):
    async def scenario():
        clock, bridge = Clock(), FakeBridge()
        session = await ReplaySession(registry(match_count),
                                       config=configuration(gpu_workers=workers, max_restarts=1,
                                                            max_estimated_cost_usd=2 if workers == 4 else 1), bridge=bridge,
                                       now=clock, monotonic=clock, session_id="session").initialize()
        session.connect("viewer")
        session.receive("viewer", playback(session))
        await session._control_tick()

        def failure(epoch):
            result = scores(epoch=epoch)
            result.update(state="error", scores=[], health={}, error_type="ConnectionClosedError",
                          reason="processing_error", error_phase="control")
            if workers > 1:
                result.update(reason="shard_error", error_type=None, error_phase=None,
                              shard_errors={str(workers - 1): {"reason": "processing_error",
                                                  "error_type": "ConnectionClosedError", "error_phase": "control"}})
            return result

        error = failure(0)
        assert not session.accept_snapshot(error)
        assert not session._finished and session._restarts == 1
        assert session.error_code == "inference_unavailable"
        assert not session.accept_snapshot(error) and session._restarts == 1
        await session._control_tick()
        assert session._handle is None and session.clock_epoch == 1
        assert not session.accept_snapshot(error)  # Previous socket cannot revive its old clock.
        clock.value += 4.9
        session.receive("viewer", playback(session, position=4.9))
        await session._control_tick()
        assert len([call for call in bridge.calls if call[0] == "start"]) == 1
        clock.value += 0.2
        session.receive("viewer", playback(session, position=5.1))
        await session._control_tick()
        starts = [call[1] for call in bridge.calls if call[0] == "start"]
        assert len(starts) == 2 and starts[-1]["clock_epoch"] == 1
        assert starts[-1]["start_position"] == 5.1 and starts[-1]["gpu_workers"] == workers
        assert 0 < session.metrics["reserved_compute_usd"] <= session.config.max_estimated_cost_usd
        assert starts[-1]["max_estimated_cost_usd"] < starts[0]["max_estimated_cost_usd"]
        session.accept_snapshot(failure(1))
        await session._control_tick()
        clock.value += 6
        session.receive("viewer", playback(session, position=11.1))
        await session._control_tick()
        assert session._restarts == 2
        assert len([call for call in bridge.calls if call[0] == "start"]) == 2
        assert session.metrics["worker_stop_succeeded"]
        await session.close()

    asyncio.run(scenario())


def test_two_shard_transport_recovery_cannot_exceed_aggregate_allowance():
    async def scenario():
        clock, bridge = Clock(), FakeBridge()
        session = await ReplaySession(registry(7), config=configuration(gpu_workers=2, max_estimated_cost_usd=0.5),
                                       bridge=bridge, now=clock, monotonic=clock, session_id="session").initialize()
        session.connect("viewer")
        session.receive("viewer", playback(session))
        await session._control_tick()
        error = scores()
        error.update(state="error", scores=[], health={}, reason="shard_error",
                     shard_errors={"0": {"reason": "processing_error", "error_phase": "publication",
                                          "error_type": "TimeoutError"}})
        session.accept_snapshot(error)
        await session._control_tick()
        assert not session._finished
        clock.value += 6
        session.receive("viewer", playback(session, position=6))
        await session._control_tick()
        assert session._finished and session.error_code == "session_budget_reached"
        assert len([call for call in bridge.calls if call[0] == "start"]) == 1
        assert session.metrics["reserved_compute_usd"] < 0.5
        await session.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("ended", [True, False])
def test_seek_restarts_closed_eof_shard_group_but_keeps_active_shards_on_normal_seek(ended):
    async def scenario():
        clock, bridge = Clock(), FakeBridge()
        session = await ReplaySession(registry(), config=configuration(), bridge=bridge,
                                       now=clock, monotonic=clock, session_id="session").initialize()
        session.connect("viewer")
        session.receive("viewer", playback(session, position=10))
        await session._control_tick()
        session._worker_ready = True
        session._set_state("running")
        session.worker_health = {"cam-1": {"status": "healthy"},
                                  "cam-2": {"status": "eof" if ended else "healthy"}}
        clock.value += 0.2
        session.receive("viewer", playback(session, position=1))
        assert session.clock_epoch == 1
        assert session._stop_requested is ended
        if ended:
            assert session.state == "starting" and not session._worker_ready
        await session._control_tick()
        starts = [call[1] for call in bridge.calls if call[0] == "start"]
        assert len(starts) == (2 if ended else 1)
        assert session.clock_epoch == 1  # The seek already invalidated the old epoch.
        if ended:
            assert starts[-1]["start_position"] == 1 and starts[-1]["clock_epoch"] == 1
            assert any(call[0] == "stop" for call in bridge.calls)
            assert starts[-1]["max_estimated_cost_usd"] < starts[0]["max_estimated_cost_usd"]
        stale_eof = scores(epoch=0, sequence=99)
        stale_eof.update(state="stopped", reason="all_sources_ended", scores=[], health={"cam-2": "eof"})
        assert not session.accept_snapshot(stale_eof)
        assert not session._finished and session.clock_epoch == 1
        await session.close()

    asyncio.run(scenario())


def test_partial_eof_seek_restart_uses_existing_allowance_instead_of_creating_budget():
    async def scenario():
        bridge = FakeBridge()
        session = await ReplaySession(registry(), config=configuration(max_estimated_cost_usd=0.2), bridge=bridge,
                                       session_id="session").initialize()
        session.connect("viewer")
        session.receive("viewer", playback(session, position=10))
        await session._control_tick()
        session.worker_health = {"cam-2": {"status": "eof"}}
        session.receive("viewer", playback(session, position=0))
        await session._control_tick()
        assert session.error_code == "session_budget_reached" and session._finished
        assert session._handle is None
        assert len([call for call in bridge.calls if call[0] == "start"]) == 1
        assert session.metrics["reserved_compute_usd"] < 0.2
        await session.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("error", [
    {"reason": "checkpoint_unavailable", "error_phase": "load"},
    {"reason": "processing_error", "error_phase": "reader"},
    {"reason": "shard_error", "shard_errors": {
        "0": {"reason": "processing_error", "error_phase": "control"},
        "1": {"reason": "checkpoint_unavailable", "error_phase": "validate"}}},
])
def test_checkpoint_or_non_transport_failures_remain_terminal(error):
    async def scenario():
        bridge = FakeBridge()
        session = await ReplaySession(registry(), config=configuration(), bridge=bridge,
                                       session_id="session").initialize()
        session.connect("viewer")
        session.receive("viewer", playback(session))
        await session._control_tick()
        snapshot = scores()
        snapshot.update(state="error", scores=[], **error)
        session.accept_snapshot(snapshot)
        assert session._finished and session._restarts == 0 and session.error_code == "worker_error"
        await session._control_tick()
        assert session._handle is None
        assert len([call for call in bridge.calls if call[0] == "start"]) == 1
        await session.close()

    asyncio.run(scenario())
