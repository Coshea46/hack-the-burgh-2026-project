"""Deterministic orchestration tests; no media, CUDA, paid service or wall waits."""

import copy
from collections import deque
from concurrent.futures import Future
from types import SimpleNamespace

import numpy as np
import pytest

from backend.ml_inference import replay_runner
from backend.ml_inference.replay_media import MediaTimelineError, Sample


class Clock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def time(self):
        return 1000 + self.now

    def perf_counter(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class InlinePool:
    def __init__(self, **kwargs):
        self.closed = False

    def submit(self, function, *args, **kwargs):
        future = Future()
        try:
            future.set_result(function(*args, **kwargs))
        except Exception as exc:  # noqa: BLE001 -- reproduce Future exception transport.
            future.set_exception(exc)
        return future

    def shutdown(self, **kwargs):
        self.closed = True


class Harness:
    def __init__(self, monkeypatch, *, matches=2, seconds=30):
        self.clock = Clock()
        monkeypatch.setattr(replay_runner, 'time', self.clock)
        monkeypatch.setattr(replay_runner, 'ThreadPoolExecutor', InlinePool)
        self.spec = {
            'session_id': 'unit-session', 'mode': 'features_mock',
            'model_version': 'features-mock-v1', 'max_duration_seconds': seconds,
            'max_estimated_cost_usd': 1,
            'matches': [{'match_id': f'match-{i}', 'source_url': f'https://example.test/{i}',
                         'offset_seconds': 120 + 10 * i} for i in range(matches)],
        }
        self.cursors, self.features, self.published, self.detected = [], [], [], []
        self.current_permit = 0
        self.epoch = 0
        self.end_index = None
        self.fail_first_reader = False
        self.fail_first_prime = False
        self.fail_audio = False
        self.always_fail_open = False
        self.control_override = None
        owner = self

        class Cursor:
            def __init__(self, url, *, offset_seconds, start_index):
                if owner.always_fail_open:
                    raise OSError('https://private.invalid/video?secret=never-log-this')
                self.key = int(url.rsplit('/', 1)[1])
                self.offset, self.next_index = offset_seconds, start_index
                self.closed = False
                self.fail = owner.fail_first_reader and not owner.cursors
                self.prime_fail = owner.fail_first_prime and not owner.cursors
                self.metadata = {'width': 24, 'height': 16, 'fps': 15, 'has_audio': True}
                self.permits = []
                self.prime_positions = []
                owner.cursors.append(self)

            def prime(self, permit):
                assert permit + 1e-8 >= self.next_index / 15
                self.prime_positions.append(permit)
                if self.prime_fail:
                    raise OSError('https://private.invalid/prime?secret=never-log-this')

            def pull(self, permit, limit=16):
                assert not self.closed and 1 <= limit <= 16
                assert not self.permits or permit >= self.permits[-1]
                self.permits.append(permit)
                if self.fail and self.next_index >= 30:
                    raise MediaTimelineError('True audio timestamp discontinuity')
                if owner.end_index is not None and self.next_index >= owner.end_index:
                    raise EOFError('Source endpoint')
                result = []
                while len(result) < limit and (self.next_index + 0.5) / 15 <= permit + 1e-8:
                    if owner.end_index is not None and self.next_index >= owner.end_index:
                        break
                    rgb = np.zeros((16, 24, 3), np.uint8)
                    rgb[0, 0, 0], rgb[0, 0, 1] = self.next_index % 250, self.key
                    result.append(Sample(self.next_index, rgb, self.offset + self.next_index / 15))
                    self.next_index += 1
                return result

            def audio_window(self, start, end):
                assert end <= owner.current_permit + 1e-8 and end - start == 5
                if owner.fail_audio:
                    raise MediaTimelineError('Audio window is incomplete')
                return np.zeros((80000, 2), np.float32)

            @property
            def stats(self):
                return {'next_sample_index': self.next_index, 'audio_history_bytes': 0}

            def close(self):
                self.closed = True

        class Features:
            def __init__(self, key, detector, **kwargs):
                self.key = key
                self.offset = kwargs['timeline_origin_seconds']
                self.epochs = [kwargs['source_epoch']]
                self.cache = deque(maxlen=75)
                self.appended, self.assembled = [], []
                self.last_result = None
                owner.features.append(self)

            def append_batch(self, indexes, frames, source_times, *, detections):
                assert list(indexes) == list(range(indexes[0], indexes[0] + len(indexes)))
                if self.cache:
                    assert indexes[0] == self.cache[-1] + 1
                for index, rgb, pts, raw in zip(indexes, frames, source_times, detections, strict=True):
                    assert (index + 0.5) / 15 <= owner.current_permit + 1e-8
                    assert pts == self.offset + index / 15
                    assert raw == (int(rgb[0, 0, 1]), index % 250)
                    self.cache.append(index)
                    self.appended.append((self.epochs[-1], index))

            def assemble(self, end, audio):
                assert list(self.cache) == list(range(end - 75, end))
                assert end / 15 <= owner.current_permit + 1e-8
                assert audio.shape == (80000, 2)
                self.assembled.append(end)
                result = np.zeros((75, 215), np.float32)
                result[:, 0] = end
                result[:, 214] = 1
                self.last_result = SimpleNamespace(timings={'total': 0, 'detector': 0})
                return result

            def reset_epoch(self, epoch):
                assert epoch != self.epochs[-1]
                self.epochs.append(epoch)
                self.cache.clear()

            @property
            def stats(self):
                return {'cache_samples': len(self.cache), 'cache_rgb_bytes': 0}

        class Detector:
            def detect(self, frames):
                assert 1 <= len(frames) <= 16
                values = [(int(f[0, 0, 1]), int(f[0, 0, 0])) for f in frames]
                owner.detected.extend((owner.epoch, *value) for value in values)
                return values

        class Scorer:
            def predict_scores(self, tensors):
                assert tensors
                return {key: 0.25 + 0.01 * int(key.rsplit('-', 1)[1]) for key in tensors}

        self.cursor_factory, self.feature_factory = Cursor, Features
        self.detector, self.scorer = Detector(), Scorer()

    def control(self):
        value = {
            'session_id': self.spec['session_id'], 'active': True, 'playing': True,
            'position': self.clock.now, 'clock_epoch': self.epoch, 'expires_at': 2000,
        }
        if self.control_override is not None:
            value.update(self.control_override(self))
        self.current_permit = value['position']
        self.epoch = value['clock_epoch']
        return value

    def run(self):
        return replay_runner.run_replay_session(
            self.spec, self.detector, self.control,
            lambda payload: self.published.append(copy.deepcopy(payload)),
            scorer=self.scorer, cursor_factory=self.cursor_factory,
            feature_factory=self.feature_factory,
        )


def test_shared_batches_preserve_match_state_and_never_read_past_viewer_watermark(monkeypatch):
    harness = Harness(monkeypatch)
    harness.control_override = lambda h: {
        'active': not (len(h.features) == 2 and all(len(f.assembled) == 3 for f in h.features)),
    }
    result = harness.run()
    assert result['reason'] == 'control_stopped'
    assert all(f.assembled == [75, 105, 135] for f in harness.features)
    assert len(harness.detected) == 270
    assert len(set(harness.detected)) == len(harness.detected)
    assert result['metrics']['detector_frames'] == 270
    assert result['metrics']['max_queue_samples'] <= 32
    assert all(c.closed for c in harness.cursors)
    assert all(score['score_kind'] == 'mock' for score in result['scores'])
    assert all(score['observation_start'] == 4 and score['observation_end'] == 9 for score in result['scores'])
    for score in result['scores']:
        offset = next(m['offset_seconds'] for m in harness.spec['matches'] if m['match_id'] == score['match_id'])
        assert score['source_timestamp'] == offset + 9
    assert any(p['state'] == 'ready' for p in harness.published)


def test_eof_closes_streams_and_stops_after_the_last_complete_window(monkeypatch):
    harness = Harness(monkeypatch)
    harness.end_index = 75
    result = harness.run()
    assert result['reason'] == 'all_sources_ended'
    assert all(f.assembled == [75] for f in harness.features)
    assert result['metrics']['detector_frames'] == 150
    assert all(c.closed for c in harness.cursors)
    assert all(h['status'] == 'eof' for h in result['health'].values())


def test_partial_eof_cannot_emit_a_short_window_or_fake_audio_score(monkeypatch):
    harness = Harness(monkeypatch, matches=1)
    harness.end_index = 60
    result = harness.run()
    assert result['reason'] == 'all_sources_ended'
    assert not harness.features[0].assembled
    assert result['scores'] == [] and result['metrics']['windows'] == 0


def test_pause_freezes_processing_and_expires_idle_worker(monkeypatch):
    harness = Harness(monkeypatch, matches=1, seconds=60)
    harness.control_override = lambda h: {'playing': False, 'position': 0}
    result = harness.run()
    assert result['reason'] == 'paused'
    assert not harness.detected
    assert all(c.closed for c in harness.cursors)
    assert 30 <= harness.clock.now < 31


def test_lease_expiry_stops_without_processing_future_media(monkeypatch):
    harness = Harness(monkeypatch, matches=1)
    harness.control_override = lambda h: {'expires_at': 1000.05}
    result = harness.run()
    assert result['reason'] == 'lease_expired'
    assert all(c.closed for c in harness.cursors)
    assert result['metrics']['windows'] == 0


def test_seek_epoch_discards_pending_observations_and_uses_new_start_index(monkeypatch):
    harness = Harness(monkeypatch, matches=1)

    def control(h):
        if h.clock.now < 0.5:
            return {'clock_epoch': 0}
        return {'clock_epoch': 1, 'position': 20 + h.clock.now - 0.5,
                'active': not any(f.assembled for f in h.features[1:])}

    harness.control_override = control
    result = harness.run()
    assert len(harness.features) == 2
    assert harness.features[0].assembled == []
    assert harness.features[1].assembled == [375]
    assert harness.features[1].appended[0] == ('1:0', 300)
    assert result['scores'][0]['clock_epoch'] == 1
    assert result['scores'][0]['observation_end'] == 25
    assert all(c.closed for c in harness.cursors)


def test_timestamp_gap_recovery_uses_a_new_epoch_and_no_cross_gap_window(monkeypatch):
    harness = Harness(monkeypatch, matches=1)
    harness.fail_first_reader = True
    harness.control_override = lambda h: {'active': not any(f.assembled for f in h.features)}
    result = harness.run()
    features = harness.features[0]
    assert features.epochs == ['0:0', '0:1']
    assert features.assembled and features.assembled[0] >= 135
    assert result['metrics']['decoder_failures'] == 1
    assert any(p['health'].get('match-0', {}).get('status') == 'error' for p in harness.published)
    assert all(c.closed for c in harness.cursors)


def test_permanent_open_failure_is_bounded_and_does_not_log_source_credentials(monkeypatch):
    harness = Harness(monkeypatch, matches=1)
    harness.always_fail_open = True
    result = harness.run()
    assert result['reason'] == 'all_sources_ended'
    assert result['metrics']['decoder_failures'] == 3
    assert result['scores'] == []
    assert 'never-log-this' not in str(harness.published)
    assert 'private.invalid' not in str(harness.published)
    assert not any(p['state'] == 'ready' for p in harness.published)


def test_unavailable_audio_never_uses_silence_or_emits_a_score(monkeypatch):
    harness = Harness(monkeypatch, matches=1, seconds=40)
    harness.fail_audio = True
    result = harness.run()
    assert result['reason'] == 'all_sources_ended'
    assert result['scores'] == []
    assert not harness.features[0].assembled
    assert all(c.closed for c in harness.cursors)
    assert result['health']['match-0']['status'] == 'error'


def test_backward_clock_requires_an_explicit_new_epoch_and_still_closes_reader(monkeypatch):
    harness = Harness(monkeypatch, matches=1)
    harness.control_override = lambda h: {'position': h.clock.now if h.clock.now < 1 else 0}
    with pytest.raises(RuntimeError, match='Replay session failed'):
        harness.run()
    assert all(c.closed for c in harness.cursors)
    assert harness.published[-1]['state'] == 'error'


def test_epoch_change_closes_a_completed_open_that_was_not_yet_harvested(monkeypatch):
    class DelayedVisibility(Future):
        def __init__(self):
            super().__init__()
            self.checks = 0

        def done(self):
            self.checks += 1
            return self.checks > 1

    class DelayedOpenPool(InlinePool):
        def submit(self, function, *args, **kwargs):
            future = DelayedVisibility()
            try:
                future.set_result(function(*args, **kwargs))
            except Exception as exc:  # noqa: BLE001 -- reproduce Future exception transport.
                future.set_exception(exc)
            return future

    harness = Harness(monkeypatch, matches=1)
    monkeypatch.setattr(replay_runner, 'ThreadPoolExecutor', DelayedOpenPool)
    harness.control_override = lambda h: {
        'active': h.clock.now < .04, 'clock_epoch': int(h.clock.now > .005),
    }
    harness.run()
    assert len(harness.cursors) == 2
    assert all(c.closed for c in harness.cursors)


def delayed_visual_pool(harness, monkeypatch, *, delay=.2):
    """CPU futures remain pending until due or explicitly awaited after YOLO."""
    futures, events, shutdowns = [], [], []

    class VisualFuture(Future):
        def __init__(self, function, args, kwargs):
            super().__init__()
            self.function, self.args, self.kwargs = function, args, kwargs
            self.features = args[0].features
            self.ready_at = harness.clock.now + delay
            self.features._test_visual_busy = True
            self.add_done_callback(lambda future: setattr(self.features, '_test_visual_busy', False))

        def finish(self):
            if super().done():
                return
            events.append(('visual_result', len(harness.detected)))
            if self.set_running_or_notify_cancel():
                try:
                    self.set_result(self.function(*self.args, **self.kwargs))
                except Exception as exc:  # noqa: BLE001 -- reproduce Future exception transport.
                    self.set_exception(exc)

        def done(self):
            if harness.clock.now >= self.ready_at:
                self.finish()
            return super().done()

        def result(self, timeout=None):
            self.finish()
            return super().result(timeout=timeout)

    class PipelinePool(InlinePool):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.visual = kwargs.get('thread_name_prefix') == 'replay-visual'

        def submit(self, function, *args, **kwargs):
            if not self.visual:
                return super().submit(function, *args, **kwargs)
            features = args[0].features
            assert not any(f.features is features and not Future.done(f) for f in futures)
            events.append(('visual_submit', len(harness.detected)))
            future = VisualFuture(function, args, kwargs)
            futures.append(future)
            return future

        def shutdown(self, **kwargs):
            shutdowns.append((self.visual, kwargs))
            super().shutdown(**kwargs)

    feature_class = harness.feature_factory
    original_stats = feature_class.stats.fget

    def safe_stats(features):
        # In production this property takes the append lock. Calling it while
        # measurements run would block the processing/publication thread.
        assert not getattr(features, '_test_visual_busy', False)
        return original_stats(features)

    monkeypatch.setattr(feature_class, 'stats', property(safe_stats))
    monkeypatch.setattr(replay_runner, 'ThreadPoolExecutor', PipelinePool)
    return futures, events, shutdowns


def test_next_detector_batch_runs_before_waiting_for_previous_visual_measurements(monkeypatch):
    harness = Harness(monkeypatch)
    futures, events, _ = delayed_visual_pool(harness, monkeypatch)
    harness.control_override = lambda h: {
        'position': 0 if h.clock.now == 0 else 9,
        'active': not (len(h.features) == 2 and all(len(f.assembled) == 3 for f in h.features)),
    }
    result = harness.run()
    first_submit = next(count for event, count in events if event == 'visual_submit')
    first_wait = next(count for event, count in events if event == 'visual_result')
    assert first_submit == 16 and first_wait >= 32  # Another YOLO batch overlapped CPU work.
    assert all(f.assembled == [75, 105, 135] for f in harness.features)
    assert len(harness.detected) == len(set(harness.detected)) == 270
    assert result['metrics']['max_visual_pending'] <= 2
    assert result['metrics']['max_queue_samples'] <= 32
    assert all(Future.done(f) for f in futures)
    for payload in harness.published:
        for health in payload['health'].values():
            assert health['next_sample_index'] <= health['scheduled_sample_index']
            if health['visual_pending_samples']:
                assert health['next_sample_index'] < health['scheduled_sample_index']


def test_stop_cancels_pending_cpu_work_without_waiting_or_claiming_it_was_processed(monkeypatch):
    harness = Harness(monkeypatch, matches=1)
    futures, _, shutdowns = delayed_visual_pool(harness, monkeypatch, delay=100)
    harness.control_override = lambda h: {
        'position': 0 if h.clock.now == 0 else 2, 'active': h.clock.now < .03,
    }
    result = harness.run()
    assert futures and all(f.cancelled() for f in futures)
    assert harness.features[0].appended == []
    health = result['health']['match-0']
    assert health['next_sample_index'] == 0 and health['scheduled_sample_index'] == 16
    assert health['visual_pending_samples'] == 16
    assert (True, {'wait': False, 'cancel_futures': True}) in shutdowns
    assert all(c.closed for c in harness.cursors)


def test_seek_discards_old_pending_cpu_job_before_new_epoch_features_are_used(monkeypatch):
    harness = Harness(monkeypatch, matches=1)
    futures, _, _ = delayed_visual_pool(harness, monkeypatch, delay=100)

    def control(h):
        return {
            'clock_epoch': int(h.clock.now >= .03), 'active': h.clock.now < .06,
            'position': (0 if h.clock.now == 0 else 2) if h.clock.now < .03 else 20.5,
        }

    harness.control_override = control
    result = harness.run()
    assert len(harness.features) == 2
    assert harness.features[0].appended == []
    assert futures[0].cancelled()
    assert result['clock_epoch'] == 1
    assert result['health']['match-0']['next_sample_index'] == 330
    assert all(c.closed for c in harness.cursors)


def test_visual_failure_discards_detected_followup_rows_and_recovers_in_a_new_epoch(monkeypatch):
    harness = Harness(monkeypatch, matches=1)
    delayed_visual_pool(harness, monkeypatch)
    original_append = harness.feature_factory.append_batch
    failed = False

    def append(features, *args, **kwargs):
        nonlocal failed
        if not failed:
            failed = True
            raise MediaTimelineError('Measurement failure')
        return original_append(features, *args, **kwargs)

    monkeypatch.setattr(harness.feature_factory, 'append_batch', append)
    harness.control_override = lambda h: {'active': not any(f.assembled for f in h.features)}
    result = harness.run()
    features = harness.features[0]
    assert features.epochs == ['0:0', '0:1']
    assert all(epoch == '0:1' for epoch, index in features.appended)
    assert result['metrics']['visual_failures'] == 1
    assert result['metrics']['source_failure_types'] == {'visual:MediaTimelineError': 1}
    assert result['health']['match-0']['last_error_phase'] == 'visual'
    assert result['health']['match-0']['last_error_type'] == 'MediaTimelineError'


def test_reader_failure_waits_for_running_visual_job_before_resetting_mutable_features(monkeypatch):
    harness = Harness(monkeypatch, matches=1)
    harness.fail_first_reader = True
    futures, _, _ = delayed_visual_pool(harness, monkeypatch, delay=2)

    def control(h):
        for future in futures:
            # Mirror CPU jobs that have begun: cancel cannot interrupt them.
            future.cancel = lambda: False
        return {
            'position': 0 if h.clock.now == 0 else 4 + max(0, h.clock.now - 1.5),
            'active': not any(f.assembled for f in h.features),
        }

    original_reset = harness.feature_factory.reset_epoch

    def reset(features, epoch):
        assert not getattr(features, '_test_visual_busy', False)
        assert all(Future.done(future) for future in futures)
        return original_reset(features, epoch)

    monkeypatch.setattr(harness.feature_factory, 'reset_epoch', reset)
    harness.control_override = control
    result = harness.run()
    assert result['reason'] == 'control_stopped'
    assert harness.features[0].epochs == ['0:0', '0:1']
    assert harness.features[0].assembled[0] >= 165
    assert result['metrics']['source_failure_types'] == {'reader:MediaTimelineError': 1}
    assert result['health']['match-0']['last_error_phase'] == 'reader'


def test_ready_windows_are_all_submitted_before_waiting_for_the_first_assembly(monkeypatch):
    harness = Harness(monkeypatch)
    events = []

    class AssemblyFuture(Future):
        def __init__(self, function, args, kwargs):
            super().__init__()
            self.function, self.args, self.kwargs = function, args, kwargs

        def result(self, timeout=None):
            if not self.done():
                events.append(('wait', self.args[0].source['match_id']))
                try:
                    self.set_result(self.function(*self.args, **self.kwargs))
                except Exception as exc:  # noqa: BLE001 -- reproduce Future exception transport.
                    self.set_exception(exc)
            return super().result(timeout=timeout)

    class AssemblyPool(InlinePool):
        def submit(self, function, *args, **kwargs):
            if function.__name__ != 'assemble_visual':
                return super().submit(function, *args, **kwargs)
            events.append(('submit', args[0].source['match_id']))
            return AssemblyFuture(function, args, kwargs)

    monkeypatch.setattr(replay_runner, 'ThreadPoolExecutor', AssemblyPool)
    harness.control_override = lambda h: {
        'active': not (len(h.features) == 2 and all(f.assembled for f in h.features)),
    }
    result = harness.run()
    assert events[:4] == [('submit', 'match-0'), ('submit', 'match-1'),
                          ('wait', 'match-0'), ('wait', 'match-1')]
    assert result['metrics']['max_assembly_pending'] == 2
    assert all(f.assembled == [75] for f in harness.features)
    assert result['metrics']['windows'] == 2
    assert all(c.closed for c in harness.cursors)


def test_failed_parallel_assembly_cannot_emit_a_score_or_stop_a_healthy_match(monkeypatch):
    harness = Harness(monkeypatch)
    original_assemble = harness.feature_factory.assemble

    def assemble(features, end, audio):
        if features.key == 'match-0':
            raise ValueError('Window assembly failed')
        return original_assemble(features, end, audio)

    monkeypatch.setattr(harness.feature_factory, 'assemble', assemble)
    harness.control_override = lambda h: {'active': not any(f.assembled for f in h.features)}
    result = harness.run()
    assert result['metrics']['window_assembly_failures'] == 1
    assert result['metrics']['source_failure_types'] == {'assembly:ValueError': 1}
    assert result['metrics']['max_assembly_pending'] == 2
    assert result['health']['match-0']['last_error_phase'] == 'assembly'
    assert result['health']['match-0']['status'] == 'error'
    assert [score['match_id'] for score in result['scores']] == ['match-1']
    assert result['metrics']['windows'] == 1
    assert all(c.closed for c in harness.cursors)


def test_transient_prime_failure_closes_cursor_and_cannot_release_initial_ready_gate(monkeypatch):
    harness = Harness(monkeypatch)
    harness.fail_first_prime = True
    harness.control_override = lambda h: {'position': 0, 'playing': False, 'active': h.clock.now < 2}
    result = harness.run()
    assert harness.cursors[0].closed and harness.cursors[0].prime_positions == [0]
    assert all(c.closed for c in harness.cursors)
    ready = [p for p in harness.published if p['state'] == 'ready']
    assert ready and all(p['produced_at'] >= 1001 for p in ready)
    assert result['metrics']['decoder_failures'] == 1
    assert not harness.detected
    assert 'never-log-this' not in str(harness.published)


def test_slow_current_point_prime_can_finish_after_thirty_seconds_before_ready(monkeypatch):
    harness = Harness(monkeypatch, matches=1, seconds=100)
    original_prime = harness.cursor_factory.prime

    def slow_prime(cursor, permit):
        harness.clock.now += 35
        return original_prime(cursor, permit)

    monkeypatch.setattr(harness.cursor_factory, 'prime', slow_prime)
    harness.control_override = lambda h: {
        'position': 0, 'playing': False,
        'active': not any(p['state'] == 'ready' for p in h.published),
    }
    result = harness.run()
    assert result['reason'] == 'control_stopped'
    assert any(p['state'] == 'ready' and p['produced_at'] >= 1035 for p in harness.published)
    assert not harness.detected


def test_unready_initialization_has_a_separate_bounded_timeout(monkeypatch):
    harness = Harness(monkeypatch, matches=1, seconds=5)

    class UnreadyPool(InlinePool):
        def submit(self, function, *args, **kwargs):
            return Future()

    monkeypatch.setattr(replay_runner, 'ThreadPoolExecutor', UnreadyPool)
    harness.control_override = lambda h: {'position': 0, 'playing': False}
    result = harness.run()
    assert result['state'] == 'error' and result['reason'] == 'startup_timeout'
    assert not harness.detected


def test_future_rounded_seek_base_is_not_primed_before_its_permission_clock(monkeypatch):
    harness = Harness(monkeypatch, matches=1)
    harness.control_override = lambda h: {'position': 1, 'active': h.clock.now < .1}
    harness.run()
    assert harness.cursors[0].next_index == 30  # Rounded two-second start is still future.
    assert harness.cursors[0].prime_positions == []
    assert harness.features[0].appended == []
