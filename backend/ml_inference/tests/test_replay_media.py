"""Decoder contracts use injected AV objects and never need footage or PyAV."""

from fractions import Fraction
from types import SimpleNamespace

import numpy as np
import pytest

from backend.ml_inference.replay_media import (
    HTTP_OPTIONS,
    MediaCursor,
    MediaTimelineError,
    _native_pcm,
)

PRIVATE_SOURCE = 'https://private.example.test/source.mkv?token=secret-test-token'


class VideoFrame:
    def __init__(self, index, *, fps=25, origin=0):
        self.index = index
        self.pts = origin + index
        self.duration = 1
        self.width = self.height = 16
        self.is_corrupt = False
        self.converted = 0

    def to_ndarray(self, **kwargs):
        assert kwargs == {'format': 'rgb24'}
        self.converted += 1
        return np.full((16, 16, 3), self.index % 250, np.uint8)


class AudioFrame:
    def __init__(self, data, *, pts=0, rate=16000, time_base=None, planar=True):
        self._data = np.asarray(data)
        self.pts, self.sample_rate = pts, rate
        self.time_base = time_base or Fraction(1, rate)
        self.format = SimpleNamespace(is_planar=planar)
        channels = self._data.shape[0] if planar else 2
        self.layout = SimpleNamespace(channels=[None] * channels)
        self.samples = self._data.shape[1] if planar else self._data.size // channels

    def to_ndarray(self):
        return self._data

    @classmethod
    def from_ndarray(cls, data, *, format, layout):
        assert format == 'fltp' and layout in ('mono', 'stereo')
        return cls(data)


class Resampler:
    def __init__(self, owner, **kwargs):
        assert kwargs['rate'] == 16000
        self.owner = owner
        self.frames = []
        owner.resamplers.append(self)

    def resample(self, frame):
        if frame is None:
            self.owner.flushes += 1
            return []
        assert frame.sample_rate == 16000 and frame.time_base == Fraction(1, 16000)
        self.frames.append(frame)
        return [frame]


class Container:
    def __init__(self, frames, video_stream, audio_stream):
        self.frames = frames
        self.streams = SimpleNamespace(video=[video_stream], audio=[audio_stream])
        self.seek_calls = []
        self.closed = False

    def seek(self, timestamp, **kwargs):
        self.seek_calls.append((timestamp, kwargs))

    def decode(self, stream):
        return iter(self.frames)

    def close(self):
        self.closed = True


class AV:
    time_base = 1000000
    AudioFrame = AudioFrame

    def __init__(self, *, seconds=10, channels=2, origin=0):
        self.video = [VideoFrame(i, origin=origin * 25) for i in range(seconds * 25)]
        self.video_stream = SimpleNamespace(
            start_time=origin * 25, time_base=Fraction(1, 25), duration=seconds * 25,
            average_rate=25, codec_context=SimpleNamespace(height=16, width=16),
        )
        self.audio_stream = SimpleNamespace(
            codec_context=SimpleNamespace(layout=SimpleNamespace(channels=[None] * channels), sample_rate=16000),
        )
        self.audio = []
        for i in range(seconds * 2):
            mono = np.full(8000, i / 100, np.float32)
            data = mono[None] if channels == 1 else np.stack([mono, -mono])
            self.audio.append(AudioFrame(data, pts=origin * 16000 + i * 8000))
        self.containers = []
        self.resamplers = []
        self.flushes = 0

    def open(self, source, **kwargs):
        assert kwargs == {'timeout': (10, 5), 'options': HTTP_OPTIONS}
        assert source == PRIVATE_SOURCE
        container = Container(self.video if not self.containers else self.audio,
                              self.video_stream, self.audio_stream)
        self.containers.append(container)
        return container

    def AudioResampler(self, **kwargs):
        return Resampler(self, **kwargs)


def cursor(av=None, **kwargs):
    av = av or AV()
    return MediaCursor(PRIVATE_SOURCE, av_module=av, **kwargs), av


def collect(worker, permit):
    result = []
    while (worker.next_index + 0.5) / 15 <= permit:
        batch = worker.pull(permit)
        if not batch:
            break
        result.extend(batch)
    return result


def test_persistent_latest_before_centre_sampling_reads_each_selected_rgb_once():
    worker, av = cursor()
    samples = collect(worker, 5)
    assert [s.sample_index for s in samples] == list(range(75))
    expected = [int(np.floor((i + 0.5) * 25 / 15 + 1e-9)) for i in range(75)]
    assert [int(s.rgb[0, 0, 0]) for s in samples] == expected
    np.testing.assert_allclose([s.source_timestamp for s in samples], np.array(expected) / 25)
    assert len(av.containers) == 2
    assert [len(c.seek_calls) for c in av.containers] == [1, 1]
    assert all(f.converted == int(f.index in expected) for f in av.video)
    assert all(f.converted == 0 for f in av.video if f.index / 25 >= 5)
    assert worker.stats['rgb_history_frames'] == 1
    assert worker.metadata['audio_channels'] == 2
    assert worker.pull(5) == []


def test_prime_uses_exact_current_frame_without_sampling_or_future_rgb_at_60fps():
    av = AV()
    av.video = [VideoFrame(i) for i in range(600)]
    av.video_stream.time_base, av.video_stream.average_rate = Fraction(1, 60), 60
    av.video_stream.duration = 600
    worker, _ = cursor(av)
    worker.prime(0)
    assert worker.next_index == 0 and worker._last_permit is None
    assert worker.stats['primed']
    assert [f.index for f in av.video if f.converted] == [0]
    assert worker._video_lookahead.timestamp == pytest.approx(1 / 60)
    assert worker.stats['audio_history_bytes'] > 0
    first = worker.pull(1 / 30)
    assert len(first) == 1 and first[0].sample_index == 0
    assert first[0].source_timestamp == pytest.approx(2 / 60)


def test_priming_does_not_change_successive_sample_pixels_pts_or_window_audio():
    primed, _ = cursor()
    plain, _ = cursor()
    primed.prime(0)
    a, b = collect(primed, 5), collect(plain, 5)
    assert [s.sample_index for s in a] == [s.sample_index for s in b]
    assert [s.source_timestamp for s in a] == [s.source_timestamp for s in b]
    assert all(np.array_equal(x.rgb, y.rgb) for x, y in zip(a, b, strict=True))
    np.testing.assert_array_equal(primed.audio_window(0, 5), plain.audio_window(0, 5))


def test_future_base_cannot_be_primed_and_http_reconnect_is_bounded_without_eof_loop():
    worker, av = cursor(start_index=30)
    with pytest.raises(ValueError, match='future'):
        worker.prime(1.9)
    assert worker.next_index == 30 and not any(frame.converted for frame in av.video)
    assert worker.stats['audio_history_bytes'] == 0
    assert HTTP_OPTIONS['reconnect_max_retries'] == '2'
    assert HTTP_OPTIONS['reconnect_delay_max'] == '1'
    assert HTTP_OPTIONS['rw_timeout'] == '1000000'
    assert HTTP_OPTIONS['reconnect_on_http_error'] == '429,5xx'
    assert 'reconnect_at_eof' not in HTTP_OPTIONS
    assert av.video_stream.codec_context.thread_count == 1
    assert av.audio_stream.codec_context.thread_count == 1


def test_leaf_av_failure_class_and_phase_are_sanitized_and_retained_in_stats():
    worker, _ = cursor()

    def broken():
        raise OSError(PRIVATE_SOURCE)
        yield  # pragma: no cover

    worker._video_frames = broken()
    with pytest.raises(RuntimeError) as raised:
        worker.prime(0)
    assert worker.stats['last_av_error_type'] == 'OSError'
    assert worker.stats['last_av_error_phase'] == 'video_decode'
    assert raised.value.media_error_type == 'OSError'
    assert raised.value.media_error_phase == 'video_decode'
    assert 'secret-test-token' not in str(raised.value) + str(worker.stats)


@pytest.mark.parametrize('channels', [1, 2])
def test_native_pcm_is_cropped_before_resampling_and_stereo_does_not_cancel(channels):
    worker, av = cursor(AV(channels=channels))
    collect(worker, 7)
    result = worker.audio_window(0, 5)
    assert result.shape == ((80000,) if channels == 1 else (80000, 2))
    assert result.dtype == np.float32 and np.isfinite(result).all()
    if channels == 2:
        np.testing.assert_array_equal(result[:, 1], -result[:, 0])
        assert np.mean(result ** 2) > 0
    assert len(av.resamplers) == 1 and av.flushes == 1
    for frame in av.resamplers[0].frames:
        assert frame.pts >= 0
        assert frame.pts + frame.samples <= 5 * 16000
    second = worker.audio_window(2, 7)
    assert second.shape == result.shape
    assert av.flushes == 2  # Independent FIR boundary for each completed window.


def test_nonzero_stream_origin_and_replay_offset_preserve_source_timeline():
    worker, av = cursor(AV(seconds=12, origin=10), offset_seconds=2, start_index=30)
    samples = collect(worker, 7)
    assert samples[0].sample_index == 30
    assert samples[0].source_timestamp == pytest.approx(4)
    result = worker.audio_window(2, 7)
    assert result[0, 0] == pytest.approx(0.08)
    assert av.containers[0].seek_calls[0][0] == int((10 + 2 + 2 - 0.25) * 25)


def test_audio_is_available_at_exact_window_end_even_without_new_video_samples():
    worker, _ = cursor()
    collect(worker, 5 - 1 / 60)
    assert worker.next_index == 75
    assert worker.pull(5) == []
    assert worker.audio_window(0, 5).shape == (80000, 2)


def test_native_history_is_bounded_and_evicted_windows_fail_instead_of_padding():
    worker, _ = cursor(AV(seconds=30), max_history_seconds=12)
    collect(worker, 25)
    assert worker.stats['audio_history_bytes'] <= 12 * 16000 * 2 * 4
    with pytest.raises(MediaTimelineError, match='coverage|evicted'):
        worker.audio_window(0, 5)
    assert worker.audio_window(20, 25).shape == (80000, 2)


def test_audio_timestamp_quantization_uses_exact_sample_clock():
    av = AV()
    for frame in av.audio:
        frame.pts = round(frame.pts / 16)
        frame.time_base = Fraction(1, 1000)
    worker, _ = cursor(av)
    collect(worker, 5)
    assert np.isfinite(worker.audio_window(0, 5)).all()


def test_remuxed_fine_timebase_does_not_erase_bounded_native_clock_quantization():
    av = AV()
    for i, frame in enumerate(av.audio):
        frame.pts += (i % 3 - 1) * 10  # <=1.25ms relative to the initial anchor.
    worker, _ = cursor(av)
    collect(worker, 5)
    assert np.isfinite(worker.audio_window(0, 5)).all()
    assert worker.stats['audio_max_clock_deviation_seconds'] <= 0.002
    strict_av = AV()
    for i, frame in enumerate(strict_av.audio):
        frame.pts += (i % 3 - 1) * 10
    strict, _ = cursor(strict_av, audio_clock_tolerance_seconds=0)
    with pytest.raises(MediaTimelineError, match='discontinuity'):
        strict.pull(5)


def test_clock_policy_never_bridges_a_real_gap_or_cumulative_drift():
    av = AV()
    av.audio[4].pts += 33  # >2ms with a perfectly exact1/16000 time base.
    worker, _ = cursor(av)
    with pytest.raises(MediaTimelineError, match='discontinuity'):
        worker.pull(5)


def test_buffered_audio_lookahead_cannot_be_used_beyond_the_permit():
    worker, _ = cursor()
    worker.pull(5.01)
    with pytest.raises(MediaTimelineError, match='permitted'):
        worker.audio_window(0.02, 5.02)


def test_packed_integer_stereo_preserves_channel_order_and_full_scale():
    packed = np.array([[-32768, 32767, 16384, -16384]], np.int16)
    decoded = _native_pcm(AudioFrame(packed, planar=False))
    assert decoded.dtype == np.float32
    np.testing.assert_array_equal(decoded, [[-1, 32767 / 32768], [0.5, -0.5]])


@pytest.mark.parametrize('kind', ['gap', 'missing', 'rate', 'channels', 'nonfinite'])
def test_audio_discontinuity_never_becomes_silence(kind):
    av = AV()
    if kind == 'gap':
        av.audio[3].pts += 1600
    elif kind == 'missing':
        av.audio[3].pts = None
    elif kind == 'rate':
        av.audio[3].sample_rate = 48000
    elif kind == 'channels':
        av.audio[3] = AudioFrame(np.zeros((1, 8000), np.float32), pts=24000)
    else:
        av.audio[3]._data[0, 0] = np.nan
    worker, _ = cursor(av)
    with pytest.raises(MediaTimelineError):
        worker.pull(5)
    with pytest.raises(RuntimeError, match='failed'):
        worker.pull(5)


def test_partial_final_batch_is_returned_before_typed_eof():
    worker, _ = cursor(AV(seconds=1))
    samples = worker.pull(2, limit=16)
    assert [s.sample_index for s in samples] == list(range(15))
    assert worker.eof
    with pytest.raises(EOFError):
        worker.pull(2)


def test_invalid_video_timestamps_and_gaps_fail_explicitly():
    av = AV()
    av.video[5].pts = av.video[4].pts
    worker, _ = cursor(av)
    with pytest.raises(MediaTimelineError, match='strictly increasing'):
        worker.pull(1)


def test_oversized_metadata_is_rejected_before_audio_open_or_rgb_allocation():
    av = AV()
    av.video_stream.codec_context.width = 3840
    av.video_stream.codec_context.height = 2160
    with pytest.raises(MediaTimelineError, match='pixel frame limit'):
        cursor(av)
    assert len(av.containers) == 1 and av.containers[0].closed
    assert all(frame.converted == 0 for frame in av.video)


def test_decoded_resolution_growth_is_rejected_before_rgb_conversion():
    av = AV()
    av.video[2].width, av.video[2].height = 3840, 2160
    worker, _ = cursor(av)
    with pytest.raises(MediaTimelineError, match='changes dimensions'):
        worker.pull(.2)
    assert av.video[2].converted == 0
    assert all(frame.converted == 0 for frame in av.video[2:])


def test_lookahead_metadata_can_be_read_but_future_pixels_are_not_converted():
    worker, av = cursor()
    worker.pull(0.1)
    assert av.video[3].converted == 0  # .12s lookahead for .10s target.
    assert max(f.index for f in av.video if f.converted) <= 2


def test_low_level_errors_hide_private_source_and_close_opened_containers():
    class BrokenAV(AV):
        def open(self, source, **kwargs):
            if self.containers:
                raise OSError(PRIVATE_SOURCE)
            return super().open(source, **kwargs)

    av = BrokenAV()
    with pytest.raises(RuntimeError, match='Media open failed') as raised:
        cursor(av)
    assert 'secret' not in str(raised.value) and PRIVATE_SOURCE not in str(raised.value)
    assert av.containers[0].closed


def test_ffmpeg_logging_is_captured_on_open_seek_and_lazy_decode_reads():
    class CapturedAV(AV):
        def __init__(self):
            super().__init__()
            owner = self
            self.capture_depth, self.captures = 0, 0

            class Capture:
                def __init__(self, *, local):
                    assert local is True

                def __enter__(self):
                    owner.capture_depth += 1
                    owner.captures += 1

                def __exit__(self, *args):
                    owner.capture_depth -= 1

            self.logging = SimpleNamespace(Capture=Capture)

        def open(self, source, **kwargs):
            assert self.capture_depth > 0
            container = super().open(source, **kwargs)
            original_seek = container.seek

            def seek(*args, **kwargs):
                assert self.capture_depth > 0
                return original_seek(*args, **kwargs)

            def decode(stream):
                assert self.capture_depth > 0

                def frames():
                    for frame in container.frames:
                        assert self.capture_depth > 0
                        yield frame

                return frames()

            container.seek, container.decode = seek, decode
            return container

    worker, av = cursor(CapturedAV())
    worker.pull(0.2)
    assert av.capture_depth == 0 and av.captures >= 10
    worker.close()


@pytest.mark.parametrize('source', ['file:///secret', 'ftp://host/media', 'https://user:pass@host/video', ''])
def test_sources_are_http_only_without_explicit_local_fixture_opt_in(source):
    with pytest.raises(ValueError):
        MediaCursor(source, av_module=AV())


def test_pause_rewind_close_and_invalid_audio_window_contracts():
    worker, av = cursor()
    worker.pull(1)
    with pytest.raises(ValueError, match='backwards'):
        worker.pull(0.5)
    with pytest.raises(ValueError, match='five seconds'):
        worker.audio_window(0, 4)
    worker.close()
    worker.close()
    assert all(c.closed for c in av.containers)
    assert worker.stats['audio_history_bytes'] == 0
    with pytest.raises(RuntimeError, match='closed'):
        worker.pull(1)
