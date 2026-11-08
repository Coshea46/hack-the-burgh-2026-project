"""Live-caption control uses real session/socket code and a provider-free worker."""

import asyncio
import copy
import json
import threading

import pytest
import websockets

from backend.main import AppController
from backend.replay import ReplaySession, SessionConfig, SourceRegistry
from backend.tests.test_replay import Clock, FakeBridge, configuration, playback, scores
from backend.websocket_manager import WebSocketManager


class CaptionWorker:
    def __init__(self):
        self.calls = []

    def start(self):
        self.calls.append(("start",))

    def update(self, view):
        self.calls.append(("update", copy.deepcopy(view)))

    def stop(self, reason):
        self.calls.append(("stop", reason))

    def close(self):
        self.calls.append(("close", threading.get_ident()))
        return True

    @property
    def updates(self):
        return [call[1] for call in self.calls if call[0] == "update"]


async def setup(*, config=None, worker=None, registry=None):
    clock, published = Clock(), []
    worker = worker or CaptionWorker()
    session = await ReplaySession(registry or SourceRegistry.from_env({"MATCHPULSE_MATCH_COUNT": "2"}),
        config=config or SessionConfig(), bridge=FakeBridge(), caption_worker=worker,
        now=clock, monotonic=clock, session_id="session", publish=published.append).initialize()
    session.connect("owner")
    return session, worker, clock, published


def toggle(session, enabled=True, owner="owner"):
    return session.receive(owner, {"type": "captions", "session_id": session.session_id, "enabled": enabled})


def event(session, **values):
    view = session.caption_worker.updates[-1]
    return {"type": "caption", "session_id": session.session_id, "match_id": view["match_id"],
            "source_key": view["source_key"], "source_identity": view["source_identity"],
            "clock_epoch": session.clock_epoch, "generation": session._caption_generation,
            "provider": "elevenlabs", "model": "scribe_v2_realtime", "state": "partial",
            "text": "Synthetic provider fixture", "source_anchor_seconds": 0, **values}


def test_controller_only_caption_toggle_with_automatic_default_and_no_work_before_playback():
    async def check():
        session, worker, _, _ = await setup()
        try:
            session.connect("observer")
            assert session.caption_state()["user_enabled"] and session.caption_state()["enabled"]
            assert not worker.updates
            assert toggle(session, owner="observer")["code"] == "viewer_in_use"
            assert toggle(session, "true")["code"] == "invalid_captions"
            assert session.receive("owner", {"type": "captions", "session_id": "old", "enabled": True})["code"] == "session_mismatch"
            session.receive("owner", playback(session, position=5))
            assert len(worker.updates) == 1
            state = session.snapshot()["captions"]
            assert state["available"] and state["enabled"] and state["configured"] and state["user_enabled"]
            assert "authorized" not in state
            assert state["model"] == "scribe_v2_realtime" and state["max_audio_seconds"] == 30
        finally:
            await session.close()
    asyncio.run(check())


def test_actual_report_permit_lease_never_extrapolates_or_renews_on_background_ticks():
    async def check():
        session, worker, clock, _ = await setup()
        try:
            session.receive("owner", playback(session, position=5, rate=2))
            toggle(session)
            initial = worker.updates[-1]
            assert initial["position"] == 5 and initial["expires_at"] == 1005
            clock.value += 4
            session._update_captions()
            repeated = worker.updates[-1]
            assert repeated["position"] == 5 and repeated["expires_at"] == initial["expires_at"]
            assert repeated["report_received_at"] == 1000
            clock.value += 1
            session._update_captions()
            assert session.caption_state()["status"] == "paused"
            assert worker.calls[-1] == ("stop", "playback_inactive")
        finally:
            await session.close()
    asyncio.run(check())


@pytest.mark.parametrize("change", [{"playing": False}, {"stalled": True}, {"available": False}, {"ended": True}])
def test_pause_buffer_unavailability_and_eof_cancel_current_generation_immediately(change):
    async def check():
        session, worker, _, _ = await setup()
        try:
            session.receive("owner", playback(session, position=5))
            toggle(session)
            old = event(session)
            generation = session._caption_generation
            session.receive("owner", playback(session, position=5, **change))
            assert session._caption_generation > generation
            assert worker.calls[-1][0] == "stop"
            assert not session._accept_caption_event(old)
        finally:
            await session.close()
    asyncio.run(check())


def test_manual_switch_stops_old_audio_until_actual_ready_target_report():
    async def check():
        session, worker, _, _ = await setup()
        try:
            session.receive("owner", playback(session, position=5))
            toggle(session)
            count = len(worker.updates)
            assert session.receive("owner", {"type": "select", "session_id": "session", "match_id": "cam-2"}) is None
            assert worker.calls[-1] == ("stop", "manual_selection")
            session.receive("owner", playback(session, match_id="cam-1", position=5.1))
            assert len(worker.updates) == count
            session.receive("owner", playback(session, match_id="cam-2", position=5.1, stalled=True))
            assert len(worker.updates) == count
            session.receive("owner", playback(session, match_id="cam-2", position=5.2))
            assert worker.updates[-1]["match_id"] == "cam-2"
            assert worker.updates[-1]["source_key"] == "match-2.mp4"
        finally:
            await session.close()
    asyncio.run(check())


def test_preparing_same_source_requires_a_new_actual_ready_report():
    async def check():
        session, worker, clock, _ = await setup()
        try:
            session.receive("owner", playback(session, position=5))
            toggle(session)
            count = len(worker.updates)
            session.receive("owner", {"type": "source_preparing", "session_id": "session", "match_id": "cam-1"})
            session._update_captions()
            assert len(worker.updates) == count
            clock.value += .25
            session.receive("owner", playback(session, position=5))
            assert len(worker.updates) == count + 1
        finally:
            await session.close()
    asyncio.run(check())


def test_automatic_proposal_stops_audio_without_delaying_or_restarting_inference():
    async def check():
        session, worker, _, published = await setup(config=configuration())
        try:
            session.receive("owner", playback(session, position=5))
            toggle(session)
            old = event(session)
            session.state = "running"
            session.accept_snapshot(scores())
            recommendation = next(message for message in published if message["type"] == "recommendation")
            assert recommendation["selected_match_id"] == "cam-2"
            assert worker.calls[-1] == ("stop", "automatic_selection")
            assert not session._accept_caption_event(old)
            assert not session.bridge.calls and not session._stop_requested
        finally:
            await session.close()
    asyncio.run(check())


def test_seek_invalidates_caption_epoch_and_resumes_only_at_new_permitted_position():
    async def check():
        session, worker, _, _ = await setup()
        try:
            session.receive("owner", playback(session, position=8))
            toggle(session)
            old = event(session)
            session.receive("owner", playback(session, position=2))
            assert session.clock_epoch == 1
            assert ("stop", "seek") in worker.calls
            assert worker.updates[-1]["position"] == 2 and worker.updates[-1]["clock_epoch"] == 1
            assert not session._accept_caption_event(old)
        finally:
            await session.close()
    asyncio.run(check())


def test_disable_reenable_and_disconnect_never_reset_aggregate_wall_budget():
    async def check():
        session, worker, clock, _ = await setup()
        try:
            session.receive("owner", playback(session, position=5))
            toggle(session)
            deadline = session.caption_state()["deadline"]
            clock.value += 5
            toggle(session, False)
            toggle(session, True)
            assert session.caption_state()["deadline"] == deadline
            session.disconnect("owner")
            assert session.caption_state()["enabled"] and session.caption_state()["user_enabled"]
            assert worker.calls[-1] == ("stop", "viewer_disconnected")
            session.connect("replacement")
            toggle(session, True, owner="replacement")
            assert session.caption_state()["deadline"] == deadline
            clock.value = deadline
            session._update_captions()
            assert not session.caption_state()["enabled"]
            assert session.caption_state()["reason"] == "budget_deadline"
            assert toggle(session, True, owner="replacement")["code"] == "captions_budget_exhausted"
        finally:
            await session.close()
    asyncio.run(check())


def test_default_on_waits_through_loading_and_pause_before_arming_immutable_deadline():
    async def check():
        session, worker, clock, _ = await setup()
        try:
            assert session.caption_state()["enabled"] and session.caption_state()["deadline"] is None
            session.receive("owner", playback(session, position=0, playing=False))
            clock.value += 45
            session.receive("owner", playback(session, position=0, stalled=True))
            assert session.caption_state()["deadline"] is None and not worker.updates
            clock.value += 45
            session.receive("owner", playback(session, position=0, playing=True))
            deadline = session.caption_state()["deadline"]
            assert deadline == clock.value + 30 and worker.updates[-1]["deadline"] == deadline
            toggle(session, False)
            clock.value += 1
            toggle(session, True)
            assert session.caption_state()["deadline"] == deadline
        finally:
            await session.close()
    asyncio.run(check())


def test_explicit_off_persists_through_switch_seek_and_reconnect_until_explicit_on():
    async def check():
        session, worker, clock, _ = await setup()
        try:
            session.receive("owner", playback(session, position=5))
            deadline = session.caption_state()["deadline"]
            toggle(session, False)
            count = len(worker.updates)
            session.receive("owner", {"type": "select", "session_id": "session", "match_id": "cam-2"})
            clock.value += .25
            session.receive("owner", playback(session, match_id="cam-2", position=4))
            assert session.clock_epoch == 1
            session.disconnect("owner")
            snapshot = session.connect("replacement")
            assert snapshot["captions"]["user_enabled"] is False and snapshot["captions"]["enabled"] is False
            session.receive("replacement", playback(session, match_id="cam-2", position=4.25))
            assert len(worker.updates) == count
            toggle(session, True, owner="replacement")
            resumed = worker.updates[-1]
            assert resumed["match_id"] == "cam-2" and resumed["position"] == 4.25
            assert resumed["clock_epoch"] == 1 and resumed["deadline"] == deadline
        finally:
            await session.close()
    asyncio.run(check())


def test_on_after_off_and_expired_budget_acknowledges_intent_with_honest_stopped_state():
    async def check():
        session, worker, clock, published = await setup()
        try:
            session.receive("owner", playback(session, position=5))
            deadline = session.caption_state()["deadline"]
            toggle(session, False)
            count = len(worker.updates)
            clock.value = deadline + 1
            assert toggle(session, True)["code"] == "captions_budget_exhausted"
            state = session.caption_state()
            assert state["user_enabled"] is True and state["enabled"] is False
            assert state["status"] == "stopped" and state["reason"] == "budget_deadline"
            assert state["deadline"] == deadline and len(worker.updates) == count
            assert published[-1]["captions"] == state
        finally:
            await session.close()
    asyncio.run(check())


def test_transport_update_failure_stops_effective_state_without_autonomous_retry():
    class FailedWorker(CaptionWorker):
        def update(self, view):
            super().update(view)
            raise RuntimeError("PRIVATE_DETAILS")

    async def check():
        session, worker, _, _ = await setup(worker=FailedWorker())
        try:
            session.receive("owner", playback(session, position=5))
            count = len(worker.updates)
            for _ in range(3):
                session._update_captions()
            state = session.caption_state()
            assert state["user_enabled"] and not state["enabled"]
            assert state["reason"] == "transport_error" and len(worker.updates) == count
            assert "PRIVATE" not in json.dumps(state)
        finally:
            await session.close()
    asyncio.run(check())


@pytest.mark.parametrize("mutation", [
    {"session_id": "old"}, {"generation": 0}, {"clock_epoch": 1}, {"match_id": "cam-2"},
    {"source_key": "other.mp4"}, {"source_identity": "0" * 64}, {"model": "scribe_v2"},
    {"source_anchor_seconds": 100}, {"source_anchor_seconds": None},
    {"words": [{"text": "future", "start_seconds": 5, "end_seconds": 7}]},
    {"words": [{"text": "bad", "start_seconds": 0, "end_seconds": float("nan")}]},
])
def test_old_wrong_source_or_future_caption_text_is_never_broadcast(mutation):
    async def check():
        session, _, _, published = await setup()
        try:
            session.receive("owner", playback(session, position=5))
            toggle(session)
            assert not session._accept_caption_event(event(session, **mutation))
            assert not any(message["type"] == "caption" for message in published)
        finally:
            await session.close()
    asyncio.run(check())


def test_partial_and_committed_events_are_compact_and_keep_media_lag_distinct():
    async def check():
        session, _, _, published = await setup()
        try:
            session.receive("owner", playback(session, position=5))
            toggle(session)
            assert session._accept_caption_event(event(session, unknown_secret="DO-NOT-EXPOSE"))
            assert session._accept_caption_event(event(session, state="committed", latency_seconds=0.2,
                words=[{"text": "fixture", "start_seconds": 3, "end_seconds": 4}]))
            messages = [message for message in published if message["type"] == "caption"]
            assert [message["state"] for message in messages] == ["partial", "committed"]
            assert "words" not in messages[0] and "latency_seconds" not in messages[0]
            assert messages[1]["playback_lag_seconds"] == 1 and messages[1]["latency_seconds"] == 0.2
            assert messages[1]["received_at"] == 1000 and messages[1]["sequence"] > messages[0]["sequence"]
            assert "DO-NOT-EXPOSE" not in json.dumps(messages)
        finally:
            await session.close()
    asyncio.run(check())


def test_provider_terminal_event_disables_retry_and_drops_old_callbacks():
    async def check():
        session, worker, _, _ = await setup()
        try:
            session.receive("owner", playback(session, position=5))
            toggle(session)
            previous = event(session)
            assert session._accept_caption_event(event(session, state="error", reason="quota_exhausted", text=""))
            count = len(worker.updates)
            session._update_captions()
            assert len(worker.updates) == count and not session.caption_state()["enabled"]
            assert session.caption_state()["user_enabled"] is True
            assert not session._accept_caption_event(previous)
        finally:
            await session.close()
    asyncio.run(check())


def test_worker_callbacks_are_threadsafe_and_close_is_off_loop():
    async def check():
        session, worker, _, published = await setup()
        session.start()
        try:
            session.receive("owner", playback(session, position=5))
            toggle(session)
            await asyncio.to_thread(session.caption_event, event(session))
            await asyncio.sleep(0)
            assert any(message["type"] == "caption" for message in published)
        finally:
            await session.close()
        assert worker.calls[-1][0] == "close" and worker.calls[-1][1] != threading.get_ident()
        assert session.metrics["caption_stop_confirmed"]
    asyncio.run(check())


def test_forced_or_unconfirmed_child_stop_is_not_reported_as_confirmed():
    class UnconfirmedWorker(CaptionWorker):
        def close(self):
            return False

    async def check():
        session, _, _, _ = await setup(worker=UnconfirmedWorker())
        await session.close()
        assert session.metrics["caption_stop_confirmed"] is False
    asyncio.run(check())


@pytest.mark.parametrize("settings", [{"MATCHPULSE_CAPTIONS_ENABLED": "invalid"},
                                     {"MATCHPULSE_CAPTION_MAX_AUDIO_SECONDS": "31"},
                                     {"MATCHPULSE_CAPTION_BUDGET_USD": "0.02"}])
def test_main_live_feature_flag_and_smoke_caps_are_strict(monkeypatch, settings):
    monkeypatch.setattr("backend.main.load_local_environment", lambda: 0)
    for name, value in settings.items():
        monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        AppController(config=SessionConfig(), api_enabled=False)


@pytest.mark.parametrize("obsolete_flag", [None, "false", "invalid"])
def test_api_key_alone_configures_default_on_without_any_authorization_flag(monkeypatch, obsolete_flag):
    monkeypatch.setattr("backend.main.load_local_environment", lambda: 0)
    monkeypatch.setenv("ELEVENLABS_API_KEY", "TEST-ONLY-NEVER-CALL")
    if obsolete_flag is None:
        monkeypatch.delenv("MATCHPULSE_CAPTION_LIVE_AUTHORIZED", raising=False)
    else:
        monkeypatch.setenv("MATCHPULSE_CAPTION_LIVE_AUTHORIZED", obsolete_flag)
    worker = CaptionWorker()
    monkeypatch.setattr("backend.captions.realtime.RealtimeCaptionWorker", lambda *args, **kwargs: worker)

    async def check():
        controller = AppController(config=SessionConfig(), api_enabled=False, host="127.0.0.1", port=0)
        task = asyncio.create_task(controller.start())
        try:
            for _ in range(100):
                if controller.ws_manager.server is not None:
                    break
                await asyncio.sleep(.01)
            state = controller.session.caption_state()
            assert state["configured"] and state["available"] and state["user_enabled"] and state["enabled"]
            assert "authorized" not in state and state["deadline"] is None
            assert not worker.updates
            controller.session.connect("viewer")
            controller.session.receive("viewer", playback(controller.session, position=5))
            assert worker.updates and worker.updates[-1]["position"] == 5
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    asyncio.run(check())


@pytest.mark.parametrize("configured,feature_enabled,reason", [(False, True, "missing_key"),
                                                             (True, False, "feature_disabled")])
def test_missing_key_and_operational_kill_switch_keep_useful_default_on_intent(
        monkeypatch, configured, feature_enabled, reason):
    monkeypatch.setattr("backend.main.load_local_environment", lambda: 0)
    if configured:
        monkeypatch.setenv("ELEVENLABS_API_KEY", "TEST-ONLY-NEVER-CALL")
    monkeypatch.setenv("MATCHPULSE_CAPTIONS_ENABLED", str(feature_enabled).lower())
    controller = AppController(config=SessionConfig(), api_enabled=False)
    state = controller.session.caption_state()
    assert state["user_enabled"] is True and state["enabled"] is False
    assert state["reason"] == reason and state["configured"] is configured
    assert state["deadline"] is None and controller.session.caption_worker is None


def test_actual_socket_caption_control_and_events_share_bounded_latest_delivery():
    async def check():
        session, worker, _, _ = await setup()
        manager = WebSocketManager(session, host="127.0.0.1", port=0, origins="http://localhost:3030")
        await manager.start()
        port = manager.server.sockets[0].getsockname()[1]
        try:
            async with websockets.connect(f"ws://127.0.0.1:{port}", origin="http://localhost:3030") as socket:
                initial = json.loads(await socket.recv())
                # setup's synthetic owner is removed so this actual socket owns
                # playback and can consent to the provider-free fake worker.
                session.disconnect("owner")
                await socket.send(json.dumps(playback(session, position=5)))
                await socket.send(json.dumps({"type": "captions", "session_id": "session", "enabled": True}))
                for _ in range(10):
                    response = json.loads(await asyncio.wait_for(socket.recv(), 1))
                    if response.get("captions", {}).get("enabled"):
                        break
                assert response["captions"]["enabled"]
                assert initial["session_id"] == "session" and worker.updates
                for index in range(30):
                    assert session._accept_caption_event(event(session, text=f"fixture {index}"))
                for connection in manager.clients.values():
                    assert len(connection.pending) <= 4  # session/recommendation/error/caption only
                for _ in range(10):
                    latest = json.loads(await asyncio.wait_for(socket.recv(), 1))
                    if latest.get("type") == "caption":
                        break
                assert latest["text"] == "fixture 29"
        finally:
            await manager.close()
            await session.close()
    asyncio.run(check())
