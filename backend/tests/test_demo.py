import json

import pytest

from backend.demo import DemoBudget, configuration


@pytest.mark.parametrize("matches,workers", [(1, 1), (2, 1), (3, 2), (7, 4)])
def test_demo_uses_distinct_existing_sources_and_bounded_real_inference(matches, workers):
    registry, config, allowance = configuration(matches, 120, False)
    sources = registry.resolve()
    assert [source.match_id for source in sources] == [f"cam-{i}" for i in range(1, matches + 1)]
    assert len({source.source_url for source in sources}) == matches
    assert [source.key for source in sources] == [f"match-{i}.mp4" for i in range(1, matches + 1)]
    assert all(source.offset_seconds == 120 for source in sources)
    assert config.mode == "real" and config.mock_scores is None and config.max_restarts == 0
    assert config.gpu_workers == workers and 0 < allowance < 2


def test_offline_demo_cannot_start_monitoring():
    _, config, _ = configuration(7, 120, True)
    assert not config.monitor and config.mode == "disabled" and config.checkpoint is None


@pytest.mark.parametrize("matches,seconds", [(0, 120), (8, 120), (True, 120), (7, 29), (7, 181)])
def test_demo_rejects_unbounded_arguments(matches, seconds):
    with pytest.raises(ValueError):
        configuration(matches, seconds, False)


def test_verification_budget_is_persistent_and_keeps_uncertain_stop_reserved(tmp_path):
    ledger = DemoBudget(tmp_path)
    reservation = ledger.reserve(1.5)
    ledger.settle(reservation, 10, 4, started=True, stopped=False)
    reloaded = DemoBudget(tmp_path)
    with pytest.raises(RuntimeError, match="allowance"):
        reloaded.reserve(0.51)
    ledger.settle(reservation, 10, 4, started=True, stopped=True)
    assert 0 < json.loads((tmp_path / "budget.json").read_text())["estimated_usd"] < 1.5


def test_no_viewer_does_not_consume_gpu_estimate(tmp_path):
    ledger = DemoBudget(tmp_path)
    reservation = ledger.reserve(0.5)
    ledger.settle(reservation, 120, 4, started=False, stopped=True)
    assert ledger.data["estimated_usd"] == 0
