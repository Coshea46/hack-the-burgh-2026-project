"""Released v3 audio admission and persistent-reader compatibility, CPU only."""

import hashlib
import importlib.util
import json
import subprocess
import sys
from fractions import Fraction
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pytest

from backend.ml_inference.replay_audio import (
    DECODER_SHA256,
    LEGACY_AUDIO,
    SAMPLECLOCK_AUDIO,
    validate_aligned_pcm,
    verify_reference_decoder,
)
from backend.ml_inference.replay_media import MediaTimelineError
from backend.ml_inference.tests.test_incremental import Detector, append_range, stream
from backend.ml_inference.tests.test_replay_media import AV, collect, cursor

FIXTURES = Path(__file__).parent / 'fixtures' / 'audio_v3'
RUNTIME = Path(__file__).parents[1] / 'runtime'


def test_exact_decoder_and_released_pcm_raw_fixture_provenance():
    assert hashlib.sha256(verify_reference_decoder().read_bytes()).hexdigest() == DECODER_SHA256
    metadata = json.loads((FIXTURES / 'provenance.json').read_text())
    for filename, key in [('pcm.npy', 'pcm_file_sha256'), ('raw.npy', 'raw_file_sha256')]:
        assert hashlib.sha256((FIXTURES / filename).read_bytes()).hexdigest() == metadata[key]
    assert metadata['split'] == 'valid' and metadata['test_accessed'] is False


def test_vorbis_three_tick_jitter_is_corrected_without_changing_native_waveform():
    av = AV()
    av.audio_stream.time_base = av.audio[0].time_base = Fraction(1, 1000)
    av.audio_stream.codec_context.name = 'vorbis'
    for i, frame in enumerate(av.audio):
        frame.time_base = av.audio_stream.time_base
        frame.pts = round(frame.pts / 16) + (3 if i % 2 else 0)
    worker, _ = cursor(av, audio_contract=SAMPLECLOCK_AUDIO)
    collect(worker, 5)
    reference, _ = cursor()
    collect(reference, 5)
    np.testing.assert_array_equal(worker.audio_window(0, 5), reference.audio_window(0, 5))
    assert worker.stats['audio_clock_corrections'] == 5
    assert worker.stats['audio_max_clock_deviation_seconds'] == pytest.approx(.003)
    assert worker.stats['audio_real_discontinuities'] == 0


def test_genuine_missing_packets_remain_nan_not_silence_or_source_failure():
    av = AV()
    for frame in av.audio[4:]:
        frame.pts += 1600
    worker, _ = cursor(av, audio_contract=SAMPLECLOCK_AUDIO)
    collect(worker, 7)
    audio = worker.audio_window(0, 5)
    assert np.isnan(audio[32000:33600]).all()
    assert np.isfinite(audio[:32000]).all() and np.isfinite(audio[33600:]).all()
    assert worker.stats['audio_real_discontinuities'] == 1
    assert worker.stats['audio_clock_corrections'] == 0
    assert worker.stats['audio_recent_discontinuities'][0]['gap_seconds'] == pytest.approx(.1)
    assert all(frame.pts + frame.samples <= 80000 for frame in av.resamplers[0].frames)
    assert np.isnan(worker.audio_window(2, 7)[:1600]).all()
    legacy_av = AV()
    legacy_av.audio[4].pts += 1600
    legacy, _ = cursor(legacy_av, audio_contract=LEGACY_AUDIO)
    with pytest.raises(MediaTimelineError, match='discontinuity'):
        collect(legacy, 5)


def test_non_vorbis_never_inherits_vorbis_three_tick_envelope():
    av = AV()
    av.audio_stream.codec_context.name = 'aac'
    av.audio_stream.time_base = Fraction(1, 1000)
    for i, frame in enumerate(av.audio):
        frame.time_base = Fraction(1, 1000)
        frame.pts = round(frame.pts / 16) + (2 if i else 0)
    worker, _ = cursor(av, audio_contract=SAMPLECLOCK_AUDIO)
    collect(worker, 5)
    assert worker.stats['audio_real_discontinuities'] == 1
    assert np.isnan(worker.audio_window(0, 5)[8000:8032]).all()


def test_large_real_gap_lookahead_cannot_evict_permitted_pre_gap_audio():
    av = AV()
    for frame in av.audio[4:]:
        frame.pts += 30 * 16000
    worker, _ = cursor(av, audio_contract=SAMPLECLOCK_AUDIO)
    collect(worker, 5)
    audio = worker.audio_window(0, 5)
    assert np.isfinite(audio[:32000]).all() and np.isnan(audio[32000:]).all()
    assert worker.stats['audio_real_discontinuities'] == 1
    assert all(frame.pts + frame.samples <= 80000 for frame in av.resamplers[0].frames)


def test_real_gap_support_does_not_disguise_evicted_history_or_future_samples():
    worker, _ = cursor(AV(seconds=30), audio_contract=SAMPLECLOCK_AUDIO)
    collect(worker, 25)
    with pytest.raises(MediaTimelineError, match='evicted'):
        worker.audio_window(0, 5)
    with pytest.raises(MediaTimelineError, match='permitted'):
        worker.audio_window(21, 26)
    assert worker.stats['audio_history_bytes'] <= 12 * 16000 * 2 * 4


def test_v3_missing_stream_and_audio_eof_remain_explicit_without_stopping_video():
    av = AV()
    av.audio = av.audio[:2]
    worker, _ = cursor(av, audio_contract=SAMPLECLOCK_AUDIO)
    assert len(collect(worker, 5)) == 75
    audio = worker.audio_window(0, 5)
    assert np.isfinite(audio[:16000]).all() and np.isnan(audio[16000:]).all()
    no_audio = AV()
    original = no_audio.open

    def open_without_audio(*args, **kwargs):
        container = original(*args, **kwargs)
        container.streams.audio = []
        return container

    no_audio.open = open_without_audio
    absent, _ = cursor(no_audio, audio_contract=SAMPLECLOCK_AUDIO)
    assert len(collect(absent, 5)) == 75 and absent.audio_window(0, 5) is None
    assert absent.metadata['has_audio'] is False


@pytest.mark.parametrize('bad', [np.zeros(79999, np.float32), np.zeros(80000, np.float64),
                               np.full(80000, np.inf, np.float32), np.full(80000, 1.01, np.float32)])
def test_v3_admission_rejects_malformed_pcm_but_preserves_nan_gaps(bad):
    validate_aligned_pcm(np.full(80000, np.nan, np.float32))
    validate_aligned_pcm(None)
    with pytest.raises((ValueError, TypeError)):
        validate_aligned_pcm(bad)


def test_v3_incremental_repairs_once_with_original_source_interval_no_yolo_repeat():
    calls = []

    def repair(raw, audio, *, endpoint_seconds):
        assert np.isnan(audio[100:200]).all()
        calls.append((raw.copy(), endpoint_seconds))
        output = raw.copy()
        output[:, 210:] = [-.2, 0, .1, .3, 1]
        output[3:7, 210:] = 0
        return output

    detector = Detector()
    worker = stream(detector, audio_contract=SAMPLECLOCK_AUDIO, core_audio_repair_fn=repair,
                    timeline_origin_seconds=120.017)
    audio = np.zeros((80000, 2), np.float32)
    audio[100:200] = np.nan
    original_audio = audio.copy()
    for start, end in [(0, 75), (75, 105), (105, 135)]:
        append_range(worker, start, end)
        features = worker.assemble(end, audio)
        assert features[:, :210].tobytes() == calls[-1][0][:, :210].tobytes()
        assert calls[-1][1] == pytest.approx(120.017 + end / 15)
        assert worker.last_result.diagnostics['audio_available_intervals'] == 71
        assert worker.last_result.diagnostics['audio_decoder_sha256'] == DECODER_SHA256
    np.testing.assert_array_equal(audio, original_audio)
    assert len(calls) == 3 and detector.indexes == list(range(135))
    assert worker.stats['detector_cache_hits'] == 90
    assert worker.stats['windows_assembled'] == 3


def _released_wheel(tmp_path):
    wheels = list(RUNTIME.glob('matchpulse-*autonomous*.whl'))
    assert len(wheels) == 1, 'The verified autonomous runtime wheel must be packaged for v3 admission'
    package = tmp_path / 'released'
    with ZipFile(wheels[0]) as wheel:
        wheel.extractall(package)
    return package


def test_real_release_pcm_to_core5_matches_published_raw_preserving_visual_bytes(tmp_path):
    package = _released_wheel(tmp_path)
    script = '''
import json,sys
sys.path.insert(0,sys.argv[1])
import numpy as np
from backend.ml_inference.replay_audio import repair_v3_audio
pcm=np.load(sys.argv[2],allow_pickle=False)
expected=np.load(sys.argv[3],allow_pickle=False)
raw=expected.copy(); raw[:,210:]=np.nan
before=raw.copy()
actual=repair_v3_audio(raw,pcm,endpoint_seconds=5.0)
assert actual[:,:210].tobytes()==expected[:,:210].tobytes()
assert raw.tobytes()==before.tobytes()
assert np.array_equal(actual[:,214],expected[:,214])
np.testing.assert_allclose(actual[:,210:],expected[:,210:],atol=2e-6,rtol=1e-5)
print(json.dumps({'core5_max_absolute_difference':float(np.max(np.abs(actual[:,210:]-expected[:,210:]))),
 'availability_exact':True,'visual_bytes_exact':True}))
'''
    result = subprocess.run([_av_python(), '-B', '-c', script, str(package),
                             str(FIXTURES / 'pcm.npy'), str(FIXTURES / 'raw.npy')],
                            capture_output=True, text=True, timeout=60, check=False)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['visual_bytes_exact'] is True


def _av_python():
    if importlib.util.find_spec('av'):
        return sys.executable
    root = Path(__file__).parents[1] / '.venv-deploy'
    for path in (root / 'Scripts' / 'python.exe', root / 'bin' / 'python'):
        if path.is_file():
            return str(path)
    pytest.skip('A CPU PyAV environment is required for native decoder parity')


def test_actual_pyav_windows_match_frozen_decoder_at_native_48khz_before_resample(tmp_path):
    # Isolated CPU process: no training, footage, model, cloud or YOLO required.
    script = '''
from fractions import Fraction
import importlib.util,sys
import av
import numpy as np
from backend.ml_inference.replay_audio import verify_reference_decoder
from backend.ml_inference.replay_media import MediaCursor
path=sys.argv[1]
with av.open(path,'w') as output:
 video=output.add_stream('mpeg4',rate=25); video.width=video.height=16; video.pix_fmt='yuv420p'
 audio=output.add_stream('pcm_f32le',rate=48000); audio.layout='stereo'
 for i in range(200):
  v=av.VideoFrame.from_ndarray(np.full((16,16,3),i%200,np.uint8),format='rgb24')
  v.pts=i+1; v.time_base=Fraction(1,25)
  for packet in video.encode(v):output.mux(packet)
  t=(np.arange(1920)+i*1920)/48000
  wave=(.3*np.sin(t*2*np.pi*431)).astype(np.float32)
  a=av.AudioFrame.from_ndarray(np.stack([wave,-wave]),format='fltp',layout='stereo')
  a.pts=(i+1)*1920; a.time_base=Fraction(1,48000); a.sample_rate=48000
  for packet in audio.encode(a):output.mux(packet)
 for packet in video.encode(None):output.mux(packet)
 for packet in audio.encode(None):output.mux(packet)
spec=importlib.util.spec_from_file_location('frozen_audio',verify_reference_decoder())
reference=importlib.util.module_from_spec(spec); spec.loader.exec_module(reference)
cursor=MediaCursor(path,allow_local=True,audio_contract='sampleclock-v3')
for end in (5,7):
 while (cursor.next_index+.5)/15<=end:cursor.pull(end)
 actual=cursor.audio_window(end-5,end)
 expected,rate=reference.decode_audio_sampleclock(path,end-5,end,cursor._video_origin)
 assert rate==16000 and actual.shape==(80000,2)
 assert np.array_equal(np.isfinite(actual),np.isfinite(expected))
 np.testing.assert_allclose(actual,expected,atol=2e-6,rtol=1e-5,equal_nan=True)
 assert np.nanmean(actual**2)>.01
cursor.close()
print('native48k_stereo_windows_5_7_exact')
'''
    result = subprocess.run([_av_python(), '-B', '-c', script, str(tmp_path / 'native.mkv')],
                            capture_output=True, text=True, timeout=60, check=True)
    assert 'native48k_stereo_windows_5_7_exact' in result.stdout
