"""Offline replay bridge/readiness safety; no SDK authentication or cloud calls."""

import asyncio
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.ml_inference import replay_client
from backend.ml_inference.replay_client import OwnedReplayHandles, ReplayClient
from backend.ml_inference.tests.test_worker_definition import load_app


def session(**extra):
    return {
        "session_id": "owned-session", "mode": "features_mock",
        "model_version": "features-mock-v1", "max_duration_seconds": 20,
        "max_estimated_cost_usd": 1,
        "matches": [{"match_id": "cam-1", "source_url": "https://media.example/video.mp4?secret=private",
                     "offset_seconds": 0}], **extra,
    }


def control(**extra):
    return {"position": 0, "playing": False, "active": True,
            "expires_at": 1005, "clock_epoch": 0, **extra}


class MemoryStore:
    def __init__(self):
        self.values, self.events = {}, []

    def get(self, key, default=None):
        return copy.deepcopy(self.values.get(key, default))

    def put(self, key, value):
        self.events.append(("put", key, copy.deepcopy(value)))
        self.values[key] = copy.deepcopy(value)

    def pop(self, key, *default):
        self.events.append(("pop", key))
        return self.values.pop(key, *default)


def sdk_fixture(monkeypatch):
    store, lookups, submissions = MemoryStore(), [], []

    class Handle:
        def __init__(self, index=0):
            self.index = index

        def cancel(self, **kwargs):
            store.events.append(("cancel", kwargs, copy.deepcopy(store.values)))
            sdk.cancelled.append(self.index)
            if self.index in sdk.cancel_fail:
                raise TimeoutError('Fixture cancellation failure')

    handle = Handle()

    class Dict:
        @staticmethod
        def from_name(name, **kwargs):
            assert name == "matchpulse-inference-replay"
            assert kwargs == {"create_if_missing": True}
            return store

    class Cls:
        @staticmethod
        def from_name(app, name):
            lookups.append((app, name))

            def spawn(spec):
                submissions.append(copy.deepcopy(spec))
                index = len(submissions) - 1
                if index == sdk.fail_at:
                    raise RuntimeError('Fixture submission failure')
                owned = handle if index == 0 else Handle(index)
                sdk.handles.append(owned)
                return owned

            return lambda: SimpleNamespace(run=SimpleNamespace(spawn=spawn))

    monkeypatch.setattr(replay_client, "time", SimpleNamespace(time=lambda: 1000))
    sdk = SimpleNamespace(Dict=Dict, Cls=Cls, handles=[], cancelled=[], cancel_fail=set(), fail_at=None)
    return sdk, store, lookups, submissions, handle


def test_construction_never_imports_or_authenticates_the_sdk(monkeypatch):
    def forbidden(_):
        raise AssertionError("No SDK import was authorized by construction")

    monkeypatch.setattr(replay_client.importlib, "import_module", forbidden)
    client = ReplayClient()
    assert client.sdk is None and client._dictionary is None


def test_start_requires_fresh_lease_then_uses_only_owned_app_and_compact_spec(monkeypatch):
    sdk, store, lookups, submissions, handle = sdk_fixture(monkeypatch)
    client = ReplayClient(sdk=sdk)
    client.update_control("owned-session", control())
    owned = client.start(session())
    assert isinstance(owned, OwnedReplayHandles) and owned.handles == (handle,)
    assert owned.score_keys == ('scores:owned-session',)
    assert lookups == [("matchpulse-inference", "ReplayWorker")]
    assert submissions == [session()]
    assert store.values["control:owned-session"]["session_id"] == "owned-session"
    assert "frames" not in submissions[0] and "features" not in submissions[0]


@pytest.mark.parametrize("state", [None, control(active=False), control(expires_at=1000)])
def test_missing_inactive_expired_control_never_submits_gpu_work(monkeypatch, state):
    sdk, store, lookups, submissions, _ = sdk_fixture(monkeypatch)
    if state is not None:
        store.values["control:owned-session"] = state
    with pytest.raises(RuntimeError, match="fresh viewer clock/lease"):
        ReplayClient(sdk=sdk).start(session())
    assert lookups == [] and submissions == []


def test_stop_revokes_before_cancelling_only_owned_input_and_deletes_only_its_keys(monkeypatch):
    sdk, store, _, _, handle = sdk_fixture(monkeypatch)
    client = ReplayClient(sdk=sdk)
    store.values.update({"control:owned-session": control(), "scores:owned-session": {"score": .8},
                         "control:other-session": {"untouched": True}})
    client.stop("owned-session", handle)
    assert store.events[0][0:2] == ("put", "control:owned-session")
    assert store.events[0][2]["active"] is False
    cancellation = store.events[1]
    assert cancellation[0:2] == ("cancel", {"terminate_containers": True})
    assert cancellation[2]["control:owned-session"]["active"] is False
    assert store.values == {"control:other-session": {"untouched": True}}


def test_latest_reads_only_owned_score_and_stop_without_input_is_safe(monkeypatch):
    sdk, store, _, _, _ = sdk_fixture(monkeypatch)
    store.values["scores:owned-session"] = {"worker_sequence": 5}
    client = ReplayClient(sdk=sdk)
    assert client.latest("owned-session") == {"worker_sequence": 5}
    client.stop("owned-session", None)
    client.stop("owned-session", None)
    assert store.values == {}


def test_cancellation_rpc_failure_still_removes_owned_compact_records(monkeypatch):
    sdk, store, _, _, handle = sdk_fixture(monkeypatch)
    store.values.update({"control:owned-session": control(), "scores:owned-session": {"worker_sequence": 1}})

    def failed_cancel(**kwargs):
        assert store.values["control:owned-session"]["active"] is False
        raise TimeoutError("Cancellation RPC failed")

    handle.cancel = failed_cancel
    with pytest.raises(TimeoutError):
        ReplayClient(sdk=sdk).stop("owned-session", handle)
    assert store.values == {}


@pytest.mark.parametrize("change", [
    {"mode": "mock"}, {"mode": "real", "checkpoint": None},
    {"max_duration_seconds": 3601}, {"max_estimated_cost_usd": .01},
    {"matches": session()["matches"] * 8},
    {"matches": [{"match_id": "cam-1", "source_url": "https://user:secret@media.example/video.mp4"}]},
])
def test_bad_mode_bundle_resource_or_source_contract_fails_before_sdk(monkeypatch, change):
    sdk, store, lookups, submissions, _ = sdk_fixture(monkeypatch)
    with pytest.raises(ValueError) as error:
        ReplayClient(sdk=sdk).start(session(**change))
    assert "user:secret" not in str(error.value)
    assert lookups == [] and submissions == [] and store.events == []


def test_control_identity_is_validated_before_any_sdk_mutation(monkeypatch):
    sdk, store, _, _, _ = sdk_fixture(monkeypatch)
    with pytest.raises(ValueError, match="different session"):
        ReplayClient(sdk=sdk).update_control("owned-session", control(session_id="another"))
    assert store.events == []


def test_replay_worker_has_one_gpu_pool_zero_idle_and_no_retry(monkeypatch):
    _, registrations, volumes = load_app(monkeypatch)
    limits = registrations["ReplayWorker"]
    assert limits["gpu"] == "T4" and limits["max_containers"] == 4
    assert limits["min_containers"] == 0 and limits["buffer_containers"] == 0
    assert limits["scaledown_window"] == 5 and limits["retries"] == 0
    assert 0 < limits["timeout"] <= 4000 and 0 < limits["startup_timeout"] <= 300
    assert limits["cpu"][1] <= 8 and limits["memory"][1] <= 8192
    assert volumes == ["matchpulse-inference-models"]


def test_replay_worker_missing_bundle_publishes_only_sanitized_error(monkeypatch):
    module, _, _ = load_app(monkeypatch)
    # Production runs on Linux. Resolve the absolute volume root on Windows as
    # well so this fake runtime exercises the loader failure, not host path rules.
    monkeypatch.setattr(module, "Path", lambda value: Path(value).resolve())
    store = MemoryStore()
    store.values["control:owned-session"] = {"clock_epoch": 4}
    module.modal.Dict = SimpleNamespace(from_name=lambda *a, **kw: store)

    class MissingBundle:
        def __init__(self, *args, **kwargs):
            pass

        def prepare(self):
            raise FileNotFoundError("https://private.example/video?token=never-publish-this")

    monkeypatch.setattr("backend.ml_inference.classifiers.ResearchInterestScorer", MissingBundle)
    worker = module.ReplayWorker()
    worker.classifiers = {}
    result = worker.run(session(mode="real", model_version="gru-v1", checkpoint="v1/classifier.pt"))
    assert result["state"] == "error" and result["reason"] == "checkpoint_unavailable"
    assert result["score_kind"] == "model" and result["error_type"] == "FileNotFoundError"
    assert result['error_phase'] == 'load' and result['error_code'] == 'checkpoint_load_failed'
    assert result["clock_epoch"] == 4 and result["scores"] == []
    assert "never-publish-this" not in json.dumps(result) and "private.example" not in json.dumps(result)
    assert store.values["scores:owned-session"] == result


def test_gpu_checkpoint_mount_resolution_matches_cpu_and_preserves_escape_guard(monkeypatch, tmp_path):
    from backend.ml_inference.tests.test_classifiers import replay_fixture

    module, _, _ = load_app(monkeypatch)
    logical_root, storage_root = tmp_path / 'models-mount', tmp_path / 'resolved-volume'
    bundle_root = storage_root / 'v1'
    bundle_root.mkdir(parents=True)
    scorer, _ = replay_fixture(bundle_root)
    loaded, reloaded = [], []

    class MountedPath:
        """A portable symlink/junction stand-in; no OS symlink privilege needed."""
        def __fspath__(self):
            return str(logical_root)

        def __truediv__(self, child):
            return storage_root / child

        def resolve(self):
            return storage_root.resolve()

    mount = MountedPath()
    # This reproduces the old GPU condition: target resolves under backing
    # storage while the comparison root still names the unresolved mount.
    old_target = (mount / 'v1/classifier.pt').resolve()
    assert not old_target.is_relative_to(mount)
    monkeypatch.setattr(module, 'Path', lambda value: mount if value == '/models' else Path(value))
    monkeypatch.setattr(module.models, 'reload', lambda: reloaded.append(True))

    def loader(target, *, device):
        assert target == scorer.path.resolve() and device == 'cpu'
        loaded.append(target)
        return scorer

    monkeypatch.setattr('backend.ml_inference.classifiers.ResearchInterestScorer', loader)
    worker = module.ReplayWorker()
    worker.classifiers = {}
    spec = session(mode='real', model_version='gru-stage1-valid', checkpoint='v1/classifier.pt')
    assert worker._scorer(spec) is scorer
    assert worker._scorer(spec) is scorer  # Cached immutable version is loaded once.
    assert loaded == [scorer.path.resolve()] and reloaded == [True]
    with pytest.raises(ValueError, match='inside inference-only storage'):
        worker._scorer({**spec, 'checkpoint': '../outside.pt'})
    with pytest.raises(ValueError, match='inside inference-only storage'):
        worker._scorer({**spec, 'checkpoint': '.'})
    assert loaded == [scorer.path.resolve()] and reloaded == [True]


@pytest.mark.parametrize('phase,message,code', [
    ('resolve', 'Checkpoint must remain inside inference-only storage', 'checkpoint_path_escape'),
    ('validate', 'Replay requires dataset audit SHA256 provenance', 'checkpoint_dataset_provenance'),
    ('volume_reload', 'https://private.example/media?token=never-publish-this', 'checkpoint_volume_reload_failed'),
])
def test_checkpoint_diagnostics_publish_only_phase_and_static_codes(monkeypatch, phase, message, code):
    module, _, _ = load_app(monkeypatch)
    store = MemoryStore()
    module.modal.Dict = SimpleNamespace(from_name=lambda *a, **kw: store)
    worker = module.ReplayWorker()

    def fail(_):
        worker._scorer_phase = phase
        raise ValueError(message)

    worker._scorer = fail
    result = worker.run(session(mode='real', checkpoint='v1/classifier.pt'))
    assert result['error_phase'] == phase and result['error_code'] == code
    assert 'never-publish-this' not in json.dumps(result) and 'private.example' not in json.dumps(result)


def multi_session(count=7, **extra):
    return session(matches=[{'match_id': f'cam-{i}', 'source_url': f'https://media.example/{i}.mp4',
                             'offset_seconds': i * 10} for i in range(1, count + 1)], **extra)


def running_shard(spec, *, sequence=1, epoch=0, state='running', reason=None, end=5):
    ids = [match['match_id'] for match in spec['matches']]
    records = [{'session_id': spec['session_id'], 'match_id': key,
                'model_version': spec['model_version'], 'clock_epoch': epoch, 'sequence': sequence,
                'observation_start': end - 5, 'observation_end': end, 'produced_at': 1000,
                'score': .8 if key == 'cam-7' else .1, 'latency_seconds': .2, 'status': 'healthy'} for key in ids]
    return {'session_id': spec['session_id'], 'model_version': spec['model_version'], 'clock_epoch': epoch,
            'worker_sequence': sequence, 'score_kind': 'mock', 'state': state, 'reason': reason,
            'produced_at': 1000, 'scores': records if state == 'running' else [],
            'health': {key: {'status': 'healthy'} for key in ids},
            'metrics': {'detector_frames': 75 * len(ids), 'detector_seconds': len(ids) * .1,
                        'peak_rss_bytes': len(ids) * 1000, 'elapsed_seconds': 6,
                        'runtime': {'container_id': 'worker-' + str(spec.get('shard_id', 'single'))},
                        'streams': {key: {} for key in ids}}}


def started_shards(monkeypatch, count=7, **extra):
    sdk, store, _lookups, specs, _ = sdk_fixture(monkeypatch)
    client = ReplayClient(sdk=sdk)
    client.update_control('owned-session', control())
    # Existing merge/race regressions deliberately exercise the two-worker
    # diagnostic partition. The auto-capacity policy is tested separately.
    extra.setdefault('gpu_workers', 2 if count > 1 else 1)
    owned = client.start(multi_session(count, **extra))
    return client, sdk, store, specs, owned


@pytest.mark.parametrize('count,groups', [(1, [1]), (2, [2]), (4, [2, 2]), (5, [2, 2, 1]), (7, [2, 2, 2, 1])])
def test_default_partition_is_balanced_bounded_and_has_no_independent_parameter_pools(monkeypatch, count, groups):
    sdk, store, _, specs, _ = sdk_fixture(monkeypatch)
    client = ReplayClient(sdk=sdk)
    client.update_control('owned-session', control())
    owned = client.start(multi_session(count))
    assert [len(spec['matches']) for spec in specs] == groups
    assert len(sdk.handles) == len(groups) and len(owned.handles) == len(groups)
    assert sum(spec.get('max_estimated_cost_usd', 1) for spec in specs) == 1
    if len(groups) > 1:
        assert [spec['shard_id'] for spec in specs] == [str(index) for index in range(len(groups))]
        assert all(spec['gpu_workers'] == 1 for spec in specs)
        assert owned.score_keys == tuple(f'scores:owned-session:{index}' for index in range(len(groups)))
    else:
        assert 'shard_id' not in specs[0]
    client.stop('owned-session', owned)
    assert sdk.cancelled == list(range(len(groups))) and not store.values


def test_explicit_three_workers_balance_seven_sources_without_dropping_a_shard(monkeypatch):
    client, sdk, store, specs, owned = started_shards(monkeypatch, gpu_workers=3)
    assert [len(spec['matches']) for spec in specs] == [3, 2, 2]
    assert len(owned.handles) == 3
    assert {source['match_id'] for spec in specs for source in spec['matches']} == {f'cam-{i}' for i in range(1, 8)}
    client.stop('owned-session', owned)
    assert sdk.cancelled == [0, 1, 2] and not store.values


def test_single_gpu_benchmark_override_retains_unsharded_transport(monkeypatch):
    _, sdk, _, specs, owned = started_shards(monkeypatch, gpu_workers=1)
    assert len(sdk.handles) == 1 and len(specs[0]['matches']) == 7
    assert 'shard_id' not in specs[0] and owned.score_keys == ('scores:owned-session',)


def test_shard_mock_scores_are_filtered_without_changing_parent_configuration(monkeypatch):
    configured = {f'cam-{i}': i / 10 for i in range(1, 8)}
    _, _, _, specs, _ = started_shards(monkeypatch, mock_scores=configured)
    assert [set(spec['mock_scores']) for spec in specs] == [{f'cam-{i}' for i in range(1, 5)},
                                                          {f'cam-{i}' for i in range(5, 8)}]
    assert len(configured) == 7


def test_partial_submission_failure_revokes_lease_cancels_owned_input_and_clears_keys(monkeypatch):
    sdk, store, _, specs, _ = sdk_fixture(monkeypatch)
    sdk.fail_at = 1
    client = ReplayClient(sdk=sdk)
    client.update_control('owned-session', control())
    with pytest.raises(RuntimeError, match='submission failure'):
        client.start(multi_session())
    assert len(specs) == 2 and sdk.cancelled == [0] and not store.values
    assert client._active is None


def test_owned_bundle_cancels_every_shard_even_when_the_first_cancel_fails(monkeypatch):
    client, sdk, store, _, owned = started_shards(monkeypatch)
    sdk.cancel_fail.add(0)
    with pytest.raises(RuntimeError, match='TimeoutError'):
        client.stop('owned-session', owned)
    assert sdk.cancelled == [0, 1] and not store.values and client._active is None


def test_merge_waits_for_all_ready_and_keeps_only_one_unchanged_poll_snapshot(monkeypatch):
    client, _, store, specs, owned = started_shards(monkeypatch)
    store.put(owned.score_keys[0], running_shard(specs[0], state='ready'))
    assert client.latest('owned-session') is None
    store.put(owned.score_keys[1], running_shard(specs[1], state='starting'))
    assert client.latest('owned-session')['state'] == 'starting'
    store.put(owned.score_keys[1], running_shard(specs[1], sequence=2, state='ready'))
    ready = client.latest('owned-session')
    assert ready['state'] == 'ready'
    assert client.latest('owned-session') == ready
    ready['health'].clear()
    assert len(client.latest('owned-session')['health']) == 7


def test_merge_compact_scores_preserves_endpoints_and_aggregates_metrics(monkeypatch):
    client, _, store, specs, owned = started_shards(monkeypatch)
    for key, spec in zip(owned.score_keys, specs):
        store.put(key, running_shard(spec))
    merged = client.latest('owned-session')
    assert merged['state'] == 'running' and len(merged['scores']) == 7
    assert merged['worker_sequence'] == 1 and merged['metrics']['detector_frames'] == 525
    assert merged['metrics']['detector_seconds'] == pytest.approx(.7)
    assert merged['metrics']['peak_rss_bytes'] == 4000 and merged['metrics']['total_peak_rss_bytes'] == 7000
    assert len(merged['metrics']['runtime']['workers']) == 2
    assert len(merged['metrics']['streams']) == 7
    assert {record['observation_end'] for record in merged['scores']} == {5}
    assert client.latest('owned-session')['worker_sequence'] == 1
    store.put(owned.score_keys[0], running_shard(specs[0], sequence=2, end=7))
    mixed = client.latest('owned-session')
    assert mixed['worker_sequence'] == 2
    assert {record['observation_end'] for record in mixed['scores']} == {5, 7}


@pytest.mark.parametrize('field,bad', [('session_id', 'previous'), ('model_version', 'old'),
                                     ('clock_epoch', 1), ('score_kind', 'model')])
def test_merge_cannot_combine_different_session_model_epoch_or_mode(monkeypatch, field, bad):
    client, _, store, specs, owned = started_shards(monkeypatch)
    store.put(owned.score_keys[0], running_shard(specs[0]))
    invalid = running_shard(specs[1])
    invalid[field] = bad
    store.put(owned.score_keys[1], invalid)
    assert client.latest('owned-session') is None


def test_epoch_change_discards_old_shard_cache_and_requires_both_new_epochs(monkeypatch):
    client, _, store, specs, owned = started_shards(monkeypatch)
    for key, spec in zip(owned.score_keys, specs):
        store.put(key, running_shard(spec))
    first = client.latest('owned-session')
    client.update_control('owned-session', control(clock_epoch=1))
    assert client.latest('owned-session') is None
    store.put(owned.score_keys[0], running_shard(specs[0], epoch=1))
    assert client.latest('owned-session') is None
    store.put(owned.score_keys[1], running_shard(specs[1], epoch=1))
    updated = client.latest('owned-session')
    assert updated['clock_epoch'] == 1 and updated['worker_sequence'] > first['worker_sequence']


def test_out_of_order_shard_sequence_and_cross_shard_match_records_are_rejected(monkeypatch):
    client, _, store, specs, owned = started_shards(monkeypatch)
    for key, spec in zip(owned.score_keys, specs):
        store.put(key, running_shard(spec, sequence=3))
    assert client.latest('owned-session')
    store.put(owned.score_keys[0], running_shard(specs[0], sequence=2))
    store.put(owned.score_keys[1], running_shard(specs[1], sequence=4))
    assert client.latest('owned-session') is None
    invalid = running_shard(specs[0], sequence=4)
    invalid['scores'][0]['match_id'] = 'cam-7'
    store.put(owned.score_keys[0], invalid)
    assert client.latest('owned-session') is None


def test_error_shard_fails_fast_even_if_other_shard_never_published(monkeypatch):
    client, _, store, specs, owned = started_shards(monkeypatch)
    store.put(owned.score_keys[1], running_shard(specs[1], state='error'))
    error = client.latest('owned-session')
    assert error['state'] == 'error' and error['reason'] == 'shard_error'


@pytest.mark.parametrize('reason,result', [('paused', 'shard_stopped'), ('session_limit', 'session_limit')])
def test_non_eof_shard_exit_stops_the_group_for_bounded_backend_recovery(monkeypatch, reason, result):
    client, _, store, specs, owned = started_shards(monkeypatch)
    store.put(owned.score_keys[0], running_shard(specs[0], state='stopped', reason=reason))
    store.put(owned.score_keys[1], running_shard(specs[1]))
    merged = client.latest('owned-session')
    assert merged['state'] == 'stopped' and merged['reason'] == result


def test_ended_shard_removes_its_scores_and_continues_remaining_healthy_sources(monkeypatch):
    client, _, store, specs, owned = started_shards(monkeypatch)
    store.put(owned.score_keys[0], running_shard(specs[0], state='stopped', reason='all_sources_ended'))
    store.put(owned.score_keys[1], running_shard(specs[1]))
    merged = client.latest('owned-session')
    assert merged['state'] == 'running' and len(merged['scores']) == 3
    assert all(merged['health'][f'cam-{i}']['status'] == 'eof' for i in range(1, 5))
    store.put(owned.score_keys[1], running_shard(specs[1], state='stopped', sequence=2, reason='all_sources_ended'))
    ended = client.latest('owned-session')
    assert ended['state'] == 'stopped' and ended['reason'] == 'all_sources_ended' and not ended['scores']


def test_unstopped_owned_session_cannot_spawn_another_unbounded_worker_group(monkeypatch):
    client, sdk, _, _, _ = started_shards(monkeypatch)
    with pytest.raises(RuntimeError, match='already owns'):
        client.start(multi_session())
    assert len(sdk.handles) == 2


def test_public_sdk_rpc_deadline_cancels_the_underlying_async_operation():
    reached, cancelled = [], []

    class BlockingRPC:
        def __call__(self):
            raise AssertionError('Synchronous SDK path must not be used')

        async def aio(self):
            reached.append(True)
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.append(True)
                raise

    with pytest.raises(TimeoutError):
        replay_client._rpc(BlockingRPC(), timeout=.01)
    assert reached == [True] and cancelled == [True]


def test_every_production_rpc_uses_public_aio_while_plain_fakes_remain_supported(monkeypatch):
    sdk, store, _, _, _ = sdk_fixture(monkeypatch)
    calls = []

    class AsyncRPC:
        def __init__(self, name, function):
            self.name, self.function = name, function

        def __call__(self, *args, **kwargs):
            raise AssertionError('Synchronous SDK wrapper must not be called')

        async def aio(self, *args, **kwargs):
            calls.append(self.name)
            return self.function(*args, **kwargs)

    for name in ('get', 'put', 'pop'):
        setattr(store, name, AsyncRPC(name, getattr(store, name)))
    original_lookup = sdk.Cls.from_name

    def lookup(*args):
        worker = original_lookup(*args)()
        original_spawn = worker.run.spawn

        def spawn(spec):
            handle = original_spawn(spec)
            handle.cancel = AsyncRPC('cancel', handle.cancel)
            return handle

        worker.run.spawn = AsyncRPC('spawn', spawn)
        return lambda: worker

    sdk.Cls.from_name = lookup
    client = ReplayClient(sdk=sdk)
    client.update_control('owned-session', control())
    owned = client.start(session())
    store.values[owned.score_keys[0]] = running_shard(session())
    assert client.latest('owned-session')['state'] == 'running'
    client.stop('owned-session', owned)
    assert {'get', 'put', 'pop', 'spawn', 'cancel'} <= set(calls)
    assert not store.values
