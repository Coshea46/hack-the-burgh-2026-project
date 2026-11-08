"""Stable director policy and its actual session/socket integration, no cloud."""

import asyncio
import json
import math

import pytest
import websockets

from backend.replay import Director, ReplaySession, SessionConfig, SourceRegistry
from backend.tests.test_replay import (
    Clock,
    FakeBridge,
    configuration,
    playback,
    registry,
    scores,
)
from backend.websocket_manager import WebSocketManager


def stable(*, ids=("cam-1", "cam-2"), **kwargs):
    return Director(ids, session_id="session", model_version="mock-v1", mode="features_mock", **kwargs)


def evaluate(director, end, now, values=None, *, sequence=None, commit=False):
    snapshot = scores(values, end=end, now=now, sequence=sequence or int((end - 3) / 2), epoch=director.clock_epoch)
    assert director.ingest(snapshot, now=now, playback_position=end)
    return director.decide(now=now, playback_position=end, commit=commit)


@pytest.mark.parametrize("mode,cooldown,bonus,confirmations", [
    ("balanced", 12, 0.20, 2), ("relaxed", 20, 0.25, 3), ("all_action", 4, 0.05, 1),
])
def test_modes_have_server_owned_exact_settings(mode, cooldown, bonus, confirmations):
    d = stable(director_mode=mode)
    settings = d.state(now=1000, playback_position=0)["config"]
    assert settings == {"cooldown_seconds": cooldown, "staying_bonus": bonus,
                        "confirmations_required": confirmations, "emergency_enabled": False, "emergency_margin": 0.5}
    if mode == "balanced":
        assert stable().settings == d.settings
        assert SessionConfig.from_env({}).director_mode == mode


@pytest.mark.parametrize("env", [
    {"MATCHPULSE_DIRECTOR_MODE": "unknown"},
    {"MATCHPULSE_DIRECTOR_EMERGENCY_ENABLED": "yes"},
    {"MATCHPULSE_DIRECTOR_EMERGENCY_MARGIN": "nan"},
])
def test_invalid_operator_settings_are_rejected_before_monitoring(env):
    with pytest.raises(ValueError):
        SessionConfig.from_env(env)


def test_balanced_requires_same_challenger_two_fresh_endpoints_and_does_not_commit_proposal():
    d = stable()
    first = evaluate(d, 5, 1000)
    assert first["selected_match_id"] == "cam-1" and d.challenger_wins == 1
    assert d.decision_reason == "confirming_challenger"
    assert not d.ingest(scores(), now=1000, playback_position=5)
    assert d.decide(now=1000.1, playback_position=5) is None
    assert d.challenger_wins == 1
    second = evaluate(d, 7, 1002)
    assert second["selected_match_id"] == "cam-2" and d.challenger_wins == 2
    assert d.current_match_id == "cam-1" and not math.isfinite(d.last_automatic_switch_at)
    assert d.decide(now=1002.1, playback_position=7) is None
    assert d.latest_scores == {"cam-1": 0.4, "cam-2": 0.8}


def test_health_only_updates_and_new_sequences_for_old_windows_cannot_confirm_again():
    d = stable()
    evaluate(d, 5, 1000)
    repeated = scores(sequence=2)
    repeated["scores"] = []
    assert not d.ingest(repeated, now=1000.5, playback_position=5)
    assert d.decide(now=1000.5, playback_position=5) is None
    assert d.challenger_wins == 1
    assert not d.ingest(scores(sequence=3), now=1000.5, playback_position=5)
    assert d.decide(now=1000.5, playback_position=5) is None
    assert d.challenger_wins == 1


def test_challenger_change_current_recovery_and_missing_endpoint_restart_confirmation():
    d = stable(ids=("cam-1", "cam-2", "cam-3"))
    evaluate(d, 5, 1000, {"cam-1": 0.1, "cam-2": 0.8, "cam-3": 0.4})
    result = evaluate(d, 7, 1002, {"cam-1": 0.1, "cam-2": 0.4, "cam-3": 0.9})
    assert result["selected_match_id"] == "cam-1" and d.challenger_id == "cam-3" and d.challenger_wins == 1
    assert evaluate(d, 9, 1004, {"cam-1": 0.1, "cam-2": 0.4, "cam-3": 0.9})["selected_match_id"] == "cam-3"
    assert evaluate(d, 11, 1006, {"cam-1": 0.8, "cam-2": 0.4, "cam-3": 0.9})["selected_match_id"] == "cam-1"
    assert d.challenger_wins == 0
    evaluate(d, 13, 1008, {"cam-1": 0.1, "cam-2": 0.9, "cam-3": 0.4})
    assert evaluate(d, 17, 1012, {"cam-1": 0.1, "cam-2": 0.9, "cam-3": 0.4})["selected_match_id"] == "cam-1"
    assert d.challenger_wins == 1


def test_adjusted_tie_retains_current_even_when_other_id_sorts_first():
    d = stable(current_match_id="cam-2")
    for end, now in ((5, 1000), (7, 1002), (9, 1004)):
        assert evaluate(d, end, now, {"cam-1": 0.5, "cam-2": 0.3})["selected_match_id"] == "cam-2"
    assert d.challenger_wins == 0
    d = stable(ids=("cam-1", "cam-2", "cam-3"), current_match_id="cam-2")
    evaluate(d, 5, 1000, {"cam-1": 0.9, "cam-2": 0.1, "cam-3": 0.9})
    assert evaluate(d, 7, 1002, {"cam-1": 0.9, "cam-2": 0.1, "cam-3": 0.9})["selected_match_id"] == "cam-1"


def test_scores_continue_every_two_seconds_during_twelve_second_cooldown_then_latest_can_be_used():
    d = stable()
    d.commit_selection("cam-2", now=1000, kind="automatic", reason="challenger_confirmed")
    decisions = [evaluate(d, end, 1001 + index * 2, {"cam-1": 0.9, "cam-2": 0.1})
                 for index, end in enumerate((5, 7, 9, 11, 13, 15))]
    assert all(result["selected_match_id"] == "cam-2" for result in decisions)
    assert all(result["selection_reason"] == "automatic_cooldown" for result in decisions)
    assert d.scores_observation_end == 15 and d.challenger_wins == 2
    proposal = d.decide(now=1012, playback_position=15, commit=False)
    assert proposal["selected_match_id"] == "cam-1" and d.challenger_wins == 2
    assert d.last_automatic_switch_at == 1000  # Proposal is not acknowledgement.
    assert d.decide(now=1012.1, playback_position=15) is None


def test_expired_latest_window_never_switches_when_cooldown_ends():
    d = stable()
    d.commit_selection("cam-2", now=1000, kind="automatic")
    evaluate(d, 5, 1001, {"cam-1": 0.9, "cam-2": 0.1})
    evaluate(d, 7, 1003, {"cam-1": 0.9, "cam-2": 0.1})
    assert d.decide(now=1012, playback_position=7) is None
    assert d.current_match_id == "cam-2"


def test_session_score_poll_rechecks_cooldown_without_a_new_inference_snapshot():
    async def scenario():
        clock, bridge, emitted = Clock(), FakeBridge(), []
        session = await ReplaySession(registry(), config=configuration(director_mode="balanced"), bridge=bridge,
                                       publish=emitted.append, now=clock, monotonic=clock,
                                       session_id="session").initialize()
        # An already-active model must first acknowledge readiness. A manually
        # assigned running label alone cannot enable the production Director.
        ready = {**scores(sequence=0), "state": "ready", "scores": []}
        assert not session.accept_snapshot(ready)
        assert session.snapshot()["auto_available"]
        session.director.commit_selection("cam-2", now=1000, kind="automatic")
        for index, end in enumerate((5, 7, 9, 11, 13, 15)):
            evaluate(session.director, end, 1001 + index * 2, {"cam-1": 0.9, "cam-2": 0.1})
        session.position, clock.value = 15, 1012
        session._handle = "already-active"
        task = asyncio.create_task(session._score_loop())
        try:
            await asyncio.sleep(0.03)
            assert emitted[-1]["selected_match_id"] == "cam-1"
            assert emitted[-1]["observation_end"] == 15
            assert session.director.challenger_wins == 2
            assert all(call[0] != "start" for call in bridge.calls)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await session.close()

    asyncio.run(scenario())


def test_manual_epoch_and_mode_changes_clear_confirmation_without_reusing_the_old_window():
    d = stable()
    evaluate(d, 5, 1000)
    d.manual_select("cam-1", now=1000.5, playback_position=5)
    assert d.challenger_wins == 0 and d.manual_hold_until == 1030.5
    assert d.decide(now=1001, playback_position=5) is None
    assert evaluate(d, 7, 1002)["selection_reason"] == "manual_hold"
    d.reset(1)
    assert d.challenger_wins == 0 and d.latest_scores == {}
    evaluate(d, 5, 1004)
    d.set_mode("relaxed")
    assert d.challenger_wins == 0 and d.minimum_switch_seconds == 20
    assert d.decide(now=1004.1, playback_position=5) is None
    for end, now in ((7, 1031), (9, 1033)):
        assert evaluate(d, end, now)["selected_match_id"] == "cam-1"
    assert evaluate(d, 11, 1035)["selected_match_id"] == "cam-2"


def test_emergency_is_disabled_by_default_and_only_bypasses_confirmation_when_enabled():
    extreme = {"cam-1": 0, "cam-2": 1}
    assert evaluate(stable(), 5, 1000, extreme)["selected_match_id"] == "cam-1"
    enabled = stable(emergency_enabled=True)
    assert evaluate(enabled, 5, 1000, extreme)["selection_reason"] == "strong_challenger"
    enabled.manual_select("cam-1", now=1001)
    assert evaluate(enabled, 7, 1002, extreme)["selection_reason"] == "manual_hold"
    enabled.manual_hold_until = 0
    enabled.commit_selection("cam-2", now=1003, kind="automatic")
    assert evaluate(enabled, 9, 1004, {"cam-1": 1, "cam-2": 0})["selection_reason"] == "automatic_cooldown"


def test_unavailable_fallback_requires_auto_enabled_and_valid_scores():
    d = stable()
    snapshot = scores({"cam-2": 0.7})
    snapshot["health"]["cam-1"] = "eof"
    assert d.ingest(snapshot, now=1000, playback_position=5)
    d.set_auto(False)
    assert d.decide(now=1000, playback_position=5) is None
    assert d.current_match_id == "cam-1" and d.latest_scores == {"cam-2": 0.7}
    d.set_auto(True)
    fallback = d.decide(now=1000.1, playback_position=5)
    assert fallback["selected_match_id"] == "cam-2" and fallback["selection_kind"] == "fallback"


def test_history_records_only_changed_commits_and_is_bounded():
    d = stable()
    for index in range(150):
        d.commit_selection("cam-2" if index % 2 == 0 else "cam-1", now=1000 + index,
                           kind="manual", reason="manual_selection", playback_position=index)
    assert len(d.history) == 100 and d.history[0]["id"] == 51 and d.history[-1]["id"] == 150
    previous = d.last_switch_at
    assert not d.commit_selection(d.current_match_id, now=9999, kind="automatic")
    assert d.last_switch_at == previous and len(d.history) == 100
    assert not math.isfinite(d.last_automatic_switch_at)


async def session_with_proposal():
    clock, bridge, sent = Clock(), FakeBridge(), []
    session = await ReplaySession(registry(), config=configuration(director_mode="balanced"), bridge=bridge,
                                   publish=sent.append, now=clock, monotonic=clock, session_id="session").initialize()
    session.connect("owner")
    session.receive("owner", playback(session, position=5))
    session.accept_snapshot(scores())
    clock.value += 2
    session.receive("owner", playback(session, position=7))
    assert session.accept_snapshot(scores(end=7, sequence=2, now=clock.value))
    return session, clock, bridge, sent[-1]


def test_automatic_cooldown_starts_at_ack_and_duplicate_ack_does_not_renew_history():
    async def scenario():
        session, clock, bridge, proposal = await session_with_proposal()
        assert proposal["selected_match_id"] == "cam-2"
        assert not math.isfinite(session.director.last_automatic_switch_at)
        clock.value += 0.3
        ack = {"type": "ack", "session_id": "session", "clock_epoch": 0,
               "sequence": proposal["sequence"], "match_id": "cam-2"}
        assert session.receive("owner", ack) is None
        committed_at = session.director.last_automatic_switch_at
        assert committed_at == clock.value and len(session.director.history) == 1
        assert session.director.history[-1]["kind"] == "automatic"
        assert session.director.history[-1]["score"] == 0.8
        clock.value += 1
        assert session.receive("owner", ack) is None
        assert session.director.last_automatic_switch_at == committed_at
        assert len(session.director.history) == 1 and not bridge.calls
        await session.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("invalidate", ["expiry", "mode", "manual"])
def test_expired_or_superseded_proposals_cannot_commit_automatic_selection(invalidate):
    async def scenario():
        session, clock, _, proposal = await session_with_proposal()
        if invalidate == "expiry":
            clock.value += 4
        elif invalidate == "mode":
            session.receive("owner", {"type": "director_mode", "session_id": "session", "mode": "relaxed"})
        else:
            session.receive("owner", {"type": "select", "session_id": "session", "match_id": "cam-1"})
        error = session.receive("owner", {"type": "ack", "session_id": "session", "clock_epoch": 0,
                                           "sequence": proposal["sequence"], "match_id": "cam-2"})
        assert error["code"] == "stale_ack"
        assert session.director.current_match_id == "cam-1"
        assert not math.isfinite(session.director.last_automatic_switch_at)
        assert not session.director.history
        await session.close()

    asyncio.run(scenario())


def test_browser_playability_cannot_revive_an_unavailable_model_worker():
    async def scenario():
        session = await ReplaySession(registry(), config=configuration(), bridge=FakeBridge(),
                                       session_id="session").initialize()
        session.connect("owner")
        session.receive("owner", playback(session, position=5))
        snapshot = scores({"cam-2": 0.8}, now=session.now())
        snapshot["health"]["cam-1"] = "error"
        assert session.accept_snapshot(snapshot)
        assert not session.director.healthy["cam-1"]
        session.receive("owner", playback(session, match_id="cam-1", position=5, available=True))
        assert not session.director.healthy["cam-1"]
        await session.close()

    asyncio.run(scenario())


def test_expired_proposal_cannot_be_classified_as_automatic_by_actual_playback_feedback():
    async def scenario():
        session, clock, _, _ = await session_with_proposal()
        clock.value += 4
        session.receive("owner", playback(session, match_id="cam-2", position=7))
        assert session.director.current_match_id == "cam-2"  # The reported source is still factual.
        assert session.director.history[-1]["kind"] == "playback"
        assert not math.isfinite(session.director.last_automatic_switch_at)
        assert session.director.state(now=clock.value, playback_position=7)["auto_cooldown_until"] == clock.value + 12
        await session.close()

    asyncio.run(scenario())


def test_health_loss_invalidates_pending_ack_even_if_target_later_recovers():
    async def scenario():
        session, clock, _, proposal = await session_with_proposal()
        health = scores(end=7, sequence=3, now=clock.value)
        health.update(scores=[], health={"cam-1": "healthy", "cam-2": "error"})
        assert not session.accept_snapshot(health)
        assert not session.director.healthy["cam-2"]
        assert session._last_recommendation is None and session.director.challenger_wins == 0
        ack = {"type": "ack", "session_id": "session", "clock_epoch": 0,
               "sequence": proposal["sequence"], "match_id": "cam-2"}
        assert session.receive("owner", ack)["code"] == "stale_ack"
        assert session.director.current_match_id == "cam-1" and not session.director.history
        assert not math.isfinite(session.director.last_automatic_switch_at)
        recovered = scores(end=7, sequence=4, now=clock.value)
        recovered["scores"] = []
        session.accept_snapshot(recovered)
        assert session.director.healthy["cam-2"]
        assert session.receive("owner", ack)["code"] == "stale_ack"
        assert session.director.current_match_id == "cam-1" and not session.director.history
        await session.close()

    asyncio.run(scenario())


def test_health_loss_cannot_make_playback_feedback_an_automatic_commit():
    async def scenario():
        session, clock, _, _ = await session_with_proposal()
        health = scores(end=7, sequence=3, now=clock.value)
        health.update(scores=[], health={"cam-1": "healthy", "cam-2": "error"})
        session.accept_snapshot(health)
        session.receive("owner", playback(session, match_id="cam-2", position=7, available=True))
        assert session.director.current_match_id == "cam-2"
        assert not session.director.healthy["cam-2"]
        assert session.director.history[-1]["kind"] == "playback"
        assert not math.isfinite(session.director.last_automatic_switch_at)
        await session.close()

    asyncio.run(scenario())


def test_unready_target_playback_does_not_start_automatic_cooldown():
    async def scenario():
        session, _, _, _ = await session_with_proposal()
        session.receive("owner", playback(session, match_id="cam-2", position=7,
                                           available=False, stalled=True))
        assert session.director.current_match_id == "cam-1"
        assert not session.director.history
        assert not math.isfinite(session.director.last_automatic_switch_at)
        await session.close()

    asyncio.run(scenario())


def test_loading_target_commits_automatic_only_when_frame_becomes_ready():
    async def scenario():
        session, clock, _, proposal = await session_with_proposal()
        session.receive("owner", playback(session, match_id="cam-2", position=7,
                                           available=True, stalled=True))
        assert session.director.current_match_id == "cam-1" and not session.director.history
        assert not math.isfinite(session.director.last_automatic_switch_at)
        clock.value += 0.2
        session.receive("owner", playback(session, match_id="cam-2", position=7,
                                           available=True, stalled=False))
        assert session.director.current_match_id == "cam-2"
        assert session.director.history[-1]["kind"] == "automatic"
        assert session.director.last_automatic_switch_at == clock.value
        committed = session.director.last_automatic_switch_at
        assert session.receive("owner", {"type": "ack", "session_id": "session", "clock_epoch": 0,
                                          "sequence": proposal["sequence"], "match_id": "cam-2"}) is None
        assert len(session.director.history) == 1 and session.director.last_automatic_switch_at == committed
        await session.close()

    asyncio.run(scenario())


def test_unattributed_ready_change_still_guards_next_auto_switch_and_manual_hold_wins_fallback():
    d = stable()
    d.commit_selection("cam-2", now=1000, kind="playback", reason="playback_feedback")
    assert not math.isfinite(d.last_automatic_switch_at)
    evaluate(d, 5, 1002, {"cam-1": 0.9, "cam-2": 0.1})
    guarded = evaluate(d, 7, 1004, {"cam-1": 0.9, "cam-2": 0.1})
    assert guarded["selected_match_id"] == "cam-2" and guarded["selection_reason"] == "automatic_cooldown"
    d.manual_select("cam-2", now=1005)
    d.healthy["cam-2"] = False  # Its video can still be watched while monitoring is unavailable.
    assert evaluate(d, 9, 1006, {"cam-1": 0.9}) is None
    assert d.current_match_id == "cam-2" and d.decision_reason == "manual_hold"
    assert evaluate(d, 11, 1036, {"cam-1": 0.9})["selection_kind"] == "fallback"


@pytest.mark.parametrize("terminal", ["error", "stopped"])
def test_terminal_snapshot_revokes_cached_proposal_and_disables_timer_and_ack(terminal):
    async def scenario():
        session, clock, _, proposal = await session_with_proposal()
        ending = scores(end=7, sequence=99, now=clock.value)
        ending.update(state=terminal, scores=[], health={},
                      reason="checkpoint_unavailable" if terminal == "error" else "session_limit")
        assert not session.accept_snapshot(ending)
        assert session._last_recommendation is None and session.director.challenger_wins == 0
        assert not session._evaluate_director()
        assert session.receive("owner", {"type": "ack", "session_id": "session", "clock_epoch": 0,
                                          "sequence": proposal["sequence"], "match_id": "cam-2"})["code"] == "stale_ack"
        assert session.director.current_match_id == "cam-1" and not session.director.history
        late = scores(end=9, sequence=100, now=clock.value)
        assert not session.accept_snapshot(late)
        assert session.state in ("error", "stopped")
        await session.close()

    asyncio.run(scenario())


def test_real_socket_mode_settings_are_authoritative_and_do_not_restart_workers():
    async def scenario():
        bridge = FakeBridge()
        config = configuration(director_mode="balanced")
        session = await ReplaySession(SourceRegistry.from_env({}), config=config, bridge=bridge).initialize()
        manager = WebSocketManager(session, host="127.0.0.1", port=0)
        await manager.start()
        url = f"ws://127.0.0.1:{manager.server.sockets[0].getsockname()[1]}"
        try:
            async with websockets.connect(url) as socket:
                initial = json.loads(await socket.recv())
                assert initial["director"]["mode"] == "balanced"
                assert len(initial["matches"]) == 7
                assert [source["match_id"] for source in initial["matches"]] == [f"cam-{index}" for index in range(1, 8)]
                assert len({source["url"] for source in initial["matches"]}) == 7
                assert all(source["url"].endswith(f"match-{index}.mp4")
                           for index, source in enumerate(initial["matches"], 1))
                await socket.send(json.dumps({"type": "director_mode", "session_id": session.session_id,
                                              "mode": "relaxed"}))
                updated = json.loads(await socket.recv())
                assert updated["director"]["mode"] == "relaxed"
                assert updated["director"]["config"]["confirmations_required"] == 3
                assert updated["sequence"] > initial["sequence"]
                await socket.send(json.dumps({"type": "select", "session_id": session.session_id, "match_id": "cam-7"}))
                picked = json.loads(await socket.recv())
                assert picked["current_match_id"] == "cam-7"
                assert picked["director"]["history"][-1]["to_match_id"] == "cam-7"
                assert picked["director"]["history"][-1]["kind"] == "manual"
                await socket.send(json.dumps({"type": "director_mode", "session_id": session.session_id,
                                              "mode": ["all_action"]}))
                assert json.loads(await socket.recv())["code"] == "invalid_director_mode"
                session.connect("observer")
                assert session.receive("observer", {"type": "director_mode", "session_id": session.session_id,
                                                    "mode": "all_action"})["code"] == "viewer_in_use"
                assert not bridge.calls and session.clock_epoch == 0
        finally:
            await manager.close()
            await session.close()

    asyncio.run(scenario())
