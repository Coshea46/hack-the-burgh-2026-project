# MatchPulse audio/video inference MVP

This opt-in package does not change the existing application until imported and
called. Shared backend/frontend files and research infrastructure remain owned
by their respective developers.

## Status

The three-argument audio/video interface passed real T4 extraction, exact
full-audio research equivalence on two matches, same-worker A–B–A isolation and
all four public-method mock-score cases. The app remains deployed at zero idle
containers. Measured calls took 35.73 seconds for one window and 66.43–77.90
seconds for two: this path is too slow for the 3–10-second anticipation horizon.
See [AUDIO_VIDEO_VALIDATION.md](AUDIO_VIDEO_VALIDATION.md) for evidence and limits.
`CLOUD_VALIDATION.md` preserves the earlier L4 diagnostic history. A trained
portable full-audio GRU bundle is still required for real model predictions.

## Public interface

```python
def select_best_match(
    current_match_id: str,
    match_frames: dict[str, np.ndarray],
    match_audio: dict[str, np.ndarray],
) -> str:
    ...
```

Executable local example from the repository root; scores here are explicitly
synthetic and no GPU is invoked:

```python
import os
import numpy as np
from backend.ml_inference import select_best_match

os.environ['MATCHPULSE_ML_MODE'] = 'mock'
frames = {'match_01': np.zeros((75, 90, 160, 3), np.uint8),
          'match_02': np.zeros((75, 90, 160, 3), np.uint8)}
# Genuine digital silence is valid supplied audio, distinct from missing audio.
audio = {key: np.zeros(80000, np.float32) for key in frames}
selected = select_best_match('match_01', frames, audio)
assert selected == 'match_01'
```

Each video is exactly `(75,H,W,3)` RGB `uint8`, with H/W >=16, covering five
seconds at 15 FPS. Each waveform is normalized float32 PCM in [-1,1] at 16kHz:
`(80000,)` mono or `(80000,2)` time-major stereo. Channel-first stereo, other
dtypes/rates/lengths, nonfinite audio and amplitude overshoot are rejected.
Video and audio dictionaries must have exactly the same match IDs. Both empty
dictionaries return the current ID even without a configured execution mode.

The caller guarantees RGB, chronological order and true audio/video alignment.
There are no timestamps in this interface, so shape validation cannot prove
synchronization or infer a waveform's actual sample rate. Both modalities must
cover the same [window_start, window_start+5) observation. For frame i, upstream
selects the source frame displayed at `window_start+(i+0.5)/15` using source PTS.
The API does not resample, resize, swap color channels, drop frames or downmix.

`select_best_match_video_only(current_match_id, match_frames)` is a separate
legacy test interface. It rejects `real` mode. The production function always
requires its third argument; missing audio is never interpreted as silence.

## Modes, scoring and errors

Set `MATCHPULSE_ML_MODE` explicitly for nonempty inputs:

| Mode | Feature extraction | Scoring |
|---|---|---|
| `mock` | Validation only; no cloud | Constant/configured synthetic scores |
| `features_mock` | Actual Modal audio/visual extraction | Synthetic scores |
| `real` | Actual Modal audio/visual extraction | Trusted portable research classifier |

Fast mock defaults to 0.5 per match. It tests no feature extraction. Inject
`InferenceService(config, scorer=MockInterestScorer({...}))` for controlled
synthetic scores, then call `service.select(current_id, frames, audio)`.

The current match gets a 0.10 staying bonus. On an adjusted tie, current wins;
otherwise tied IDs use lexicographic order. Scores are finite values in [0,1].
Malformed input raises before dispatch. Missing dependencies/checkpoints,
incompatible classifiers and classifier failures raise without mock fallback.
Individual worker failures are omitted with a warning. If every extraction
fails, return the current ID without claiming a prediction. Late or unfinished
request inputs are cancelled; no automatic paid extraction retries are used.
The caller must handle a retained current ID that is absent from its dictionary.

## Research runtime and audio

`ResearchFeatureExtractor` delegates the exact raw waveform to
`MatchFeatureExtractor.extract(frames, fps=15, audio=audio,
audio_sample_rate=16000)`. It does not implement audio feature math.
Research columns 210:215 are log RMS, RMS delta, spectral flux, spectral
centroid and audio availability. Every interval must report audio_available=1
for full-audio inference. Supplied digital silence retains availability=1.
Stereo channels remain separate; research computes channel power and channel
magnitude spectra without opposite-phase cancellation.

Visual settings stay YOLO26s, 640, batch 16, person confidence 0.15, ball
confidence 0.08, FP16 and BoT-SORT, five seconds/15 FPS. Tracking/team/slot state
is window-local. Raw detection caches are cleared per request while the model
can remain warm. The unchanged pinned wheel and weight hashes are in
`runtime/provenance.json`. There is no automatic model-weight download.

## Lossless transport and resources

Versioned audio/video envelopes bind both components to one validated match ID.
RGB frames and float32 audio are zlib-compressed independently at level 1.
The decoder bounds expansion, checks complete streams, metadata, sample rate,
shapes and matching IDs, and rejects truncated/trailing/corrupt data. Samples,
pixel values, channel order and dtypes are preserved. No media files are created
by the public method. The client checks the returned match ID and audio flags.

One 720p video window is 207,360,000 raw bytes. Audio adds 320,000 bytes mono or
640,000 stereo. One feature tensor is 64,500 bytes. Actual measurements are in
the validation report; compression cannot establish production latency alone.

App: `matchpulse-inference`. Model Volume: `matchpulse-inference-models`.
Neither addresses `matchpulse-private` or its training resources. The image uses
Python 3.13, CUDA Torch 2.11.0, torchvision 0.26.0 and pinned worker dependencies.
The client supports Python >=3.10 and imports neither Modal nor Torch eagerly.

All settings use prefix `MATCHPULSE_ML_`:

| Suffix | Default |
|---|---|
| MODE | Required: mock / features_mock / real |
| CHECKPOINT | Required safe relative Volume path in real mode |
| GPU | T4 |
| WORKER_CONCURRENCY / MAX_INFLIGHT | 1 / 1 |
| SCALEDOWN_SECONDS | 5 |
| WORKER_TIMEOUT_SECONDS | 180 |
| CALL_TIMEOUT_SECONDS / REQUEST_TIMEOUT_SECONDS | 240 / 300 |
| CLASSIFIER_TIMEOUT_SECONDS | 60 |
| FP16 / STAYING_BONUS | true / 0.10 |
| MAX_WINDOW_BYTES | 536870912 raw video bytes per match |

Feature resources are 1–4 CPU cores, 2–8 GiB RAM, maximum one T4 container in
this validation, zero warm/buffer minimum. The classifier is CPU-only, two cores,
4 GiB, maximum one and minimum zero. Limits are per class variant, not global
account limits. Timeouts bound remote execution/result waits; serialization and
network cancellation mean they are not an absolute public-method latency SLA.

## Installation and authorized deployment

Install the client independently; do not change the research environment:

```powershell
py -3.12 -m venv backend/ml_inference/.venv-client
backend/ml_inference/.venv-client/Scripts/python -m pip install -e './backend/ml_inference[test,modal]'
python -B -m pytest -p no:cacheprovider backend/ml_inference/tests -q
```

For separately authorized deployment, set `MATCHPULSE_ML_WEIGHTS` to the existing
verified YOLO26s file and run from the repository root:

```powershell
backend/ml_inference/.venv-client/Scripts/python -m modal deploy -m backend.ml_inference.modal_app
```

The bounded task controller uses the existing isolated `.venv-deploy/`:

```powershell
backend/ml_inference/.venv-deploy/Scripts/python -B -m backend.ml_inference.cloud_validation deploy --allow-cloud
backend/ml_inference/.venv-deploy/Scripts/python -B -m backend.ml_inference.cloud_validation validate --allow-cloud
```

Its private `artifacts/t4-av-validation/budget.json` enforces this task's $5
additional estimated ceiling and records the prior task estimate separately.
It permits at most two deployment/equivalence attempts, not open-ended retries.
Cloud validation requires two existing authorized local broadcast samples and
decoder dependencies in that isolated client environment. Ordinary unit tests
need only NumPy/pytest, no credentials, GPU, footage or trained checkpoint.

`t4_validation.py` locally prepares test inputs. Its preprocessing keeps stereo,
normalizes PyAV input timebases and checks continuous sample clocks against PTS
quantization before resampling. It rejects discontinuities without gap filling.
This fixes local test decoding, not research source or research feature math.

## Trained classifier handoff

Obtain the trusted exported full-audio `classifier.pt` bundle from the training
owner. Training-only `best.pt` and detector weights are not classifier bundles.
Upload a versioned file into the independent inference Volume, for example:

```powershell
python -m modal volume put matchpulse-inference-models C:/trusted/export/classifier.pt v1/classifier.pt
$env:MATCHPULSE_ML_MODE = 'real'
$env:MATCHPULSE_ML_CHECKPOINT = 'v1/classifier.pt'
```

Upload is an explicit separate operation when the artifact becomes available;
no trained checkpoint was uploaded by this task. The CPU worker loads the
research portable-bundle API once per warm version. Readiness rejects missing
or incompatible bundles before feature dispatch. Require schema
`matchpulse-215-v1`, raw [75,215], five seconds/15 FPS, model_input_size=215 and
feature_indices=0..214. No-audio 210-channel bundles are rejected.
The research loader owns saved normalization, strict state loading, channel
selection, eval/inference mode and sigmoid batch predictions. No duplicate
normalizer, model training or synthetic fallback is introduced.

## Exact backend integration handoff — shared files remain unchanged

1. Extend ingestion to retain synchronized audio and source PTS alongside video.
   Decode/resample upstream to 16kHz float32 PCM, preserve mono/stereo channels,
   and deliver exactly 80,000 samples from the same complete five-second interval.
   Reject gaps; do not pad missing data or turn it into silence.
2. Deliver 75 RGB frames at interval centres. The current ingester reverses RGB
   to BGR; remove that conversion upstream or explicitly restore RGB before
   calling this package. Do not send the existing arbitrary frame count directly.
3. Correct the reversed from/to timestamps in `_generate_video_arrays`, using
   source PTS and the actual window interval. Carry the real displayed match ID
   from the controller/UI; never infer it from dictionary order.
4. In `VideoProcessor.process_chunk`, once the inputs comply, use the call below.
   Under the backend's current working directory/Docker layout, import
   `ml_inference`; from the repository root use `backend.ml_inference` instead.

```python
from ml_inference import select_best_match

match_frames = {key: data['frames'] for key, data in video_arrays.items()}
match_audio = {key: data['audio'] for key, data in video_arrays.items()}
selected = select_best_match(self.current_match_id, match_frames, match_audio)
data = video_arrays.get(selected)
if data is None:
    return None
return {'camera_id': selected,
        'from_timestamp': data['from_timestamp'],
        'to_timestamp': data['to_timestamp']}
```

5. Keep this synchronous call in the existing processing worker. Remove the
   unconditional dummy cam-1 switch. Broadcast only an accepted ordered result,
   and update current_match_id only when that switch is accepted. Reject stale
   decisions by window ID/age. Install this client's Modal dependency in the
   application image when the teammate enables it; shared requirements/Docker
   files were not changed here.

Latency must be measured against the 3–10-second anticipation horizon. Successful
extraction does not establish prediction quality, useful lead time or capacity
for seven simultaneous matches. Overlap reuse, improved batching, placing the
client near the source/GPU and any future warm-worker budget are separate work.
