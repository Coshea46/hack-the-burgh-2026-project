"""Caption tests use explicit synthetic provider fixtures, never demo captions."""

import json
import sys
import wave
from fractions import Fraction
from io import BytesIO
from types import SimpleNamespace
from urllib.error import URLError

import pytest

from backend.captions import (
    CaptionService,
    cue_at,
    source_identity,
    validate_track,
    webvtt,
)
from backend.captions.audio import decode_audio
from backend.captions.pipeline import CaptionPipeline, words_to_track
from backend.captions.provider import CaptionError, ElevenLabsTranscriber, estimate_cost
from backend.captions.schema import canonical_json


@pytest.fixture
def identity():
    return source_identity("match-1.mp4", '"synthetic-etag"', 100,
                           "https://test.invalid/match-1.mp4?signature=private")


@pytest.fixture
def track(identity):
    return words_to_track({"text": "synthetic fixture", "words": [
        {"start": .25, "end": 1.5, "text": "synthetic fixture", "type": "word", "speaker_id": "speaker_0"},
        {"start": 2, "end": 3, "text": "second fixture", "type": "word", "speaker_id": "speaker_1"}]},
        match_id="cam-1", source_key="match-1.mp4", identity=identity["digest"],
        start=120, end=150, language="en", audio_metadata={"audio_sha256": "fixture"})


def test_identity_excludes_signed_query_but_rejects_replaced_object(identity):
    renewed = source_identity("match-1.mp4", "synthetic-etag", 100,
                              "https://test.invalid/match-1.mp4?signature=renewed")
    assert identity == renewed
    assert identity["digest"] != source_identity("match-1.mp4", "changed", 100,
                                                 "https://test.invalid/match-1.mp4")["digest"]
    assert "private" not in canonical_json(identity)


def test_cue_seek_pause_and_half_open_source_boundaries(track):
    assert cue_at(track, 120.25)["text"] == "synthetic fixture"
    assert cue_at(track, 121.5) is None
    assert cue_at(track, 122.5)["text"] == "second fixture"
    assert cue_at(track, 122.5) == cue_at(track, 122.5)  # paused source clock
    assert cue_at(track, 0) is None
    assert cue_at(track, 151) is None
    assert cue_at(track, 120.3)["text"] == "synthetic fixture"  # backward seek


def test_webvtt_absolute_source_time_and_escaping(track):
    track["cues"][0]["text"] = "<script> & fixture -->"
    result = webvtt(track)
    assert "00:02:00.250 --> 00:02:01.500" in result
    assert "&lt;script&gt; &amp; fixture --&gt;" in result
    assert "not human reviewed" in result


@pytest.mark.parametrize("mutate", [
    lambda t: t["cues"][0].update(start_seconds=float("nan")),
    lambda t: t["cues"][0].update(end_seconds=151),
    lambda t: t["cues"][1].update(start_seconds=121),
    lambda t: t["cues"][0].update(text=""),
    lambda t: t.update(source_identity="unverified"),
    lambda t: t["provenance"].update(timestamp_method="guessed"),
])
def test_track_rejects_bad_timing_or_provenance(track, mutate):
    mutate(track)
    with pytest.raises(ValueError):
        validate_track(track)


def test_service_identity_isolation_and_immediate_source_switch(tmp_path, identity, track):
    (tmp_path / f"cam-1-{identity['digest']}.json").write_text(canonical_json(track), encoding="utf-8")
    service = CaptionService(tmp_path, {"cam-1": "match-1.mp4", "cam-2": "match-2.mp4"},
                             {"cam-1": identity}, identity_checker=lambda *args: identity)
    assert service.get("cam-1")["status"] == "ready"
    assert service.get("cam-2")["cues"] == []
    assert service.get("cam-1", source_key="override.mp4")["status"] == "source_mismatch"
    assert service.get("cam-1", source_identity="old")["cues"] == []
    assert service.get("../cam-1")["reason"] == "unknown_source"
    changed = CaptionService(tmp_path, {"cam-1": "match-1.mp4"}, {"cam-1": "b" * 64})
    assert changed.get("cam-1")["cues"] == []
    untrusted = CaptionService(tmp_path, {"cam-1": "match-1.mp4"})
    assert untrusted.get("cam-1", source_identity=identity["digest"])["cues"] == []


def test_corrupt_track_is_honest_unavailable(tmp_path, identity):
    (tmp_path / f"cam-1-{identity['digest']}.json").write_text("{}", encoding="utf-8")
    result = CaptionService(tmp_path, {"cam-1": "match-1.mp4"}, {"cam-1": identity}).get("cam-1")
    assert result["reason"] == "invalid_track" and result["cues"] == []


class FakeTranscriber:
    def __init__(self, fail=False):
        self.calls, self.fail = 0, fail

    def transcribe(self, wav, **kwargs):
        self.calls += 1
        if self.fail:
            raise CaptionError("provider_transport_error")
        assert wav == b"fixture-wav"
        assert kwargs == {"model": "scribe_v2", "language": "en"}
        return {"text": "fixture", "words": [{"start": 0, "end": 1, "text": "fixture", "type": "word"}]}


def generate_args(identity):
    return {"match_id": "cam-1", "source_key": "match-1.mp4", "identity": identity,
            "source_url": "https://test.invalid/match-1.mp4", "start_seconds": 120, "end_seconds": 150}


def test_dry_run_cost_never_decodes_uploads_or_writes(tmp_path, identity):
    def forbidden(*a, **k):
        pytest.fail("dry run must have no media/provider side effects")
    pipeline = CaptionPipeline(tmp_path, decoder=forbidden)
    result = pipeline.generate(**generate_args(identity))
    assert result["status"] == "estimate"
    assert result["estimated_cost_usd"] == pytest.approx(30 / 3600 * .22)
    assert estimate_cost(30, "scribe_v2") == pytest.approx(.00183333333333)
    assert list(tmp_path.iterdir()) == []


def test_completed_job_reuses_track_and_never_pays_twice(tmp_path, identity):
    transcriber = FakeTranscriber()
    pipeline = CaptionPipeline(tmp_path, transcriber=transcriber, decoder=lambda *a, **k: (b"fixture-wav", {}))
    assert pipeline.generate(**generate_args(identity), execute=True)["status"] == "complete"
    assert pipeline.generate(**generate_args(identity), execute=True)["status"] == "reused"
    assert transcriber.calls == 1
    service = CaptionService(tmp_path, {"cam-1": "match-1.mp4"}, {"cam-1": identity},
                             identity_checker=lambda *args: identity)
    assert service.get("cam-1")["cues"][0]["start_seconds"] == 120
    assert len(list(tmp_path.glob("*.vtt"))) == 1


def test_failed_uncertain_request_stays_reserved_without_retry(tmp_path, identity):
    transcriber = FakeTranscriber(fail=True)
    pipeline = CaptionPipeline(tmp_path, transcriber=transcriber, decoder=lambda *a, **k: (b"fixture-wav", {}))
    with pytest.raises(CaptionError, match="provider_transport_error"):
        pipeline.generate(**generate_args(identity), execute=True)
    with pytest.raises(CaptionError, match="already_reserved"):
        pipeline.generate(**generate_args(identity), execute=True)
    assert transcriber.calls == 1
    ledger = json.loads((tmp_path / "ledger.json").read_text())
    assert next(iter(ledger["jobs"].values()))["status"] == "failed_reserved"


def test_budget_and_unsupported_models_reject_before_upload(tmp_path, identity):
    transcriber = FakeTranscriber()
    pipeline = CaptionPipeline(tmp_path, transcriber=transcriber, decoder=lambda *a, **k: (b"fixture-wav", {}))
    with pytest.raises(CaptionError, match="duration_budget"):
        pipeline.generate(**{**generate_args(identity), "end_seconds": 151}, execute=True)
    with pytest.raises(CaptionError, match="cost_budget"):
        pipeline.generate(**generate_args(identity), max_cost_usd=.001, execute=True)
    with pytest.raises(CaptionError, match="unsupported_model"):
        pipeline.generate(**generate_args(identity), model="unsupported", execute=True)
    assert transcriber.calls == 0 and list(tmp_path.iterdir()) == []


def test_missing_key_no_decode_or_write(tmp_path, identity, monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    with pytest.raises(CaptionError, match="api_key_missing"):
        CaptionPipeline(tmp_path).generate(**generate_args(identity), execute=True)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("response", [
    {"text": "untimed text"}, {"text": "untimed text", "words": []},
    {"words": [{"start": -1, "end": 2, "text": "bad", "type": "word"}]},
    {"words": [{"start": 0, "end": 31, "text": "bad", "type": "word"}]},
    {"words": [{"start": 2, "end": 3, "text": "a", "type": "word"},
               {"start": 1, "end": 4, "text": "b", "type": "word"}]},
])
def test_provider_timestamps_never_guessed_or_repaired(response, identity):
    with pytest.raises(CaptionError):
        words_to_track(response, match_id="cam-1", source_key="match-1.mp4", identity=identity["digest"],
                          start=120, end=150, language="en", audio_metadata={})


def test_actual_provider_silence_has_coverage_and_no_invented_cues(identity):
    track = words_to_track({"text": "", "words": []}, match_id="cam-1", source_key="match-1.mp4",
                              identity=identity["digest"], start=120, end=150, language="en", audio_metadata={})
    assert not track["cues"] and track["coverage_intervals"]


def test_provider_native_timestamp_request_and_sanitized_single_attempt():
    requests = []
    def convert(**kwargs):
        requests.append(kwargs)
        assert kwargs["request_options"] == {"max_retries": 0, "timeout_in_seconds": 45}
        assert kwargs["model_id"] == "scribe_v2" and kwargs["timestamps_granularity"] == "word"
        assert kwargs["diarize"] and kwargs["tag_audio_events"] and not kwargs["use_multi_channel"]
        return {"words": [], "text": ""}
    client = SimpleNamespace(speech_to_text=SimpleNamespace(convert=convert))
    provider = ElevenLabsTranscriber("private-key", client=client)
    assert provider.transcribe(b"x" * 100)["words"] == []
    assert len(requests) == 1
    def failure(*a, **k):
        raise URLError("PRIVATE_URL_AND_KEY")
    with pytest.raises(CaptionError, match="^provider_transport_error$"):
        ElevenLabsTranscriber("private-key", client=SimpleNamespace(speech_to_text=SimpleNamespace(convert=failure))).transcribe(b"x" * 100)
    class SDKError(Exception):
        status_code = 429
    def http_failure(*a, **k):
        raise SDKError("PRIVATE_BODY")
    with pytest.raises(CaptionError, match="^provider_http_429$"):
        ElevenLabsTranscriber("private-key", client=SimpleNamespace(speech_to_text=SimpleNamespace(convert=http_failure))).transcribe(b"x" * 100)


def test_two_precomputed_intervals_keep_real_gap_and_accumulate_budget(tmp_path, identity):
    pipeline = CaptionPipeline(tmp_path, transcriber=FakeTranscriber(), decoder=lambda *a, **k: (b"fixture-wav", {}))
    pipeline.generate(**generate_args(identity), max_cost_usd=.004, execute=True)
    pipeline.generate(**{**generate_args(identity), "start_seconds": 180, "end_seconds": 210},
                      max_cost_usd=.004, execute=True)
    result = CaptionService(tmp_path, {"cam-1": "match-1.mp4"}, {"cam-1": identity},
                            identity_checker=lambda *args: identity).get("cam-1")
    assert len(result["coverage_intervals"]) == 2
    assert cue_at(result, 155) is None
    assert cue_at(result, 180)["text"] == "fixture"
    with pytest.raises(CaptionError, match="cumulative_cost_budget"):
        pipeline.generate(**{**generate_args(identity), "start_seconds": 240, "end_seconds": 270},
                          max_cost_usd=.004, execute=True)


def test_identity_cannot_be_reused_for_other_source_url_or_key(tmp_path, identity):
    with pytest.raises(CaptionError, match="source_identity_mismatch"):
        CaptionPipeline(tmp_path).generate(**{**generate_args(identity), "source_url": "https://other.invalid/match-1.mp4"})
    with pytest.raises(CaptionError, match="source_identity_mismatch"):
        CaptionPipeline(tmp_path).generate(**{**generate_args(identity), "source_key": "match-2.mp4"})


def fake_audio_av(monkeypatch, *, gap_samples=0, missing_tail=False, decoder_error=False):
    import numpy as np

    class Frame:
        def __init__(self, data, pts):
            self.data, self.pts = data, pts
            self.time_base, self.sample_rate = Fraction(1, 16000), 16000
            self.samples = data.shape[1]
            self.format = SimpleNamespace(is_planar=True, name="fltp")
            self.layout = SimpleNamespace(name="stereo", channels=[1, 2])

        def to_ndarray(self):
            return self.data

        @classmethod
        def from_ndarray(cls, data, **kwargs):
            return cls(data, 0)

    frames = [Frame(np.tile(np.array([[.1], [-.2]], dtype=np.float32), (1, 320)), 125 * 16000 - 160),
              Frame(np.tile(np.array([[.3], [-.4]], dtype=np.float32), (1, 320)), 125 * 16000 + 160 + gap_samples)]
    stream = SimpleNamespace(codec_context=SimpleNamespace(layout=frames[0].layout))
    video = SimpleNamespace(start_time=5 * 16000, time_base=Fraction(1, 16000))
    calls = []

    class Container:
        streams = SimpleNamespace(audio=[stream], video=[video])

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def seek(self, *args, **kwargs):
            calls.append(("seek", args, kwargs))

        def decode(self, selected):
            assert selected is stream  # no video frames decoded
            if decoder_error:
                raise RuntimeError("PRIVATE_URL")
            return iter(frames[:1] if missing_tail else frames)

    class Resampler:
        def __init__(self, **kwargs):
            assert kwargs == {"format": "fltp", "layout": "stereo", "rate": 16000}

        def resample(self, frame):
            if frame is not None:
                assert frame.time_base == Fraction(1, 16000)
            return [frame] if frame is not None else []

    def open_source(source, **kwargs):
        calls.append(("open", kwargs))
        return Container()

    monkeypatch.setitem(sys.modules, "av", SimpleNamespace(open=open_source, AudioResampler=Resampler,
                                                         AudioFrame=Frame, time_base=1000000))
    return calls


def test_audio_crop_preserves_stereo_native_source_clock_without_padding(monkeypatch):
    import numpy as np

    calls = fake_audio_av(monkeypatch)
    data, metadata = decode_audio("https://test.invalid/private", 120, 120.02, etag="fixture-etag")
    with wave.open(BytesIO(data)) as wav:
        assert (wav.getframerate(), wav.getnchannels(), wav.getnframes()) == (16000, 2, 320)
        values = np.frombuffer(wav.readframes(320), dtype="<i2").reshape(-1, 2) / 32767
    np.testing.assert_allclose(values[:160], np.tile([.1, -.2], (160, 1)), atol=1 / 32767)
    np.testing.assert_allclose(values[160:], np.tile([.3, -.4], (160, 1)), atol=1 / 32767)
    assert metadata["channel_policy"] == "preserved" and metadata["sample_count"] == 320
    assert metadata["max_source_clock_jitter_seconds"] == 0
    assert calls[0][1]["timeout"] == (10, 5)
    assert calls[0][1]["options"]["headers"] == 'If-Match: "fixture-etag"\r\n'


@pytest.mark.parametrize("kwargs,reason", [
    ({"gap_samples": 160}, "audio_discontinuity"),
    ({"missing_tail": True}, "audio_coverage_missing"),
    ({"decoder_error": True}, "audio_decode_RuntimeError"),
])
def test_audio_missing_or_discontinuous_data_never_becomes_silence(monkeypatch, kwargs, reason):
    fake_audio_av(monkeypatch, **kwargs)
    with pytest.raises(CaptionError, match=f"^{reason}$"):
        decode_audio("https://test.invalid/PRIVATE_URL", 120, 120.02)


def test_caption_cli_loads_local_configuration_and_checks_identity_without_provider_key(monkeypatch, capsys, tmp_path, identity):
    from backend.captions import __main__ as cli

    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    loaded, heads = [], []
    monkeypatch.setattr(cli, "load_local_environment", lambda: loaded.append(True))
    source = SimpleNamespace(match_id="cam-1", key="match-1.mp4", source_url="https://test.invalid/match-1.mp4")
    monkeypatch.setattr(cli, "SourceRegistry", SimpleNamespace(from_env=lambda: SimpleNamespace(resolve=lambda: [source])))
    def head(value):
        heads.append(value)
        return identity
    monkeypatch.setattr(cli, "head_identity", head)
    assert cli.main(["--match-id", "cam-1", "--execute", "--track-dir", str(tmp_path)]) == 2
    assert loaded == [True]
    assert heads == [source]
    assert not (tmp_path / "ledger.json").exists()
    assert json.loads(capsys.readouterr().out) == {"status": "unavailable", "reason": "api_key_missing"}


def test_completed_track_reuses_without_key_decode_or_upload(tmp_path, identity, monkeypatch):
    transcriber = FakeTranscriber()
    CaptionPipeline(tmp_path, transcriber=transcriber, decoder=lambda *a, **k: (b"fixture-wav", {})).generate(
        **generate_args(identity), execute=True)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    def forbidden(*a, **k):
        pytest.fail("completed track must not decode or upload")
    pipeline = CaptionPipeline(tmp_path, decoder=forbidden)
    result = pipeline.generate(**generate_args(identity), execute=True)
    assert result["status"] == "reused" and transcriber.calls == 1


@pytest.mark.parametrize("changes,reason", [
    ({"match_id": "cam-2"}, "completed_track_identity_mismatch"),
    ({"source_key": "match-2.mp4"}, "completed_track_identity_mismatch"),
    ({"source_identity": "b" * 64}, "completed_track_identity_mismatch"),
    ({"language": "fr", "cues": []}, "completed_track_identity_mismatch"),
    ({"coverage_intervals": [{"start_seconds": 120, "end_seconds": 149}]}, "completed_track_coverage_mismatch"),
    ({"coverage_intervals": [{"start_seconds": 120, "end_seconds": 121},
                             {"start_seconds": 122, "end_seconds": 150}]}, "completed_track_coverage_mismatch"),
])
def test_completed_reuse_rejects_foreign_or_incomplete_valid_track(tmp_path, identity, monkeypatch, changes, reason):
    transcriber = FakeTranscriber()
    CaptionPipeline(tmp_path, transcriber=transcriber, decoder=lambda *a, **k: (b"fixture-wav", {})).generate(
        **generate_args(identity), execute=True)
    path = tmp_path / f"cam-1-{identity['digest']}.json"
    track = json.loads(path.read_text(encoding="utf-8"))
    track.update(changes)
    validate_track(track)  # well-formed foreign data must still fail reuse
    path.write_text(canonical_json(track), encoding="utf-8")
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    with pytest.raises(CaptionError, match=f"^{reason}$"):
        CaptionPipeline(tmp_path).generate(**generate_args(identity), execute=True)
    assert transcriber.calls == 1


def test_cli_completed_reuse_verifies_source_without_transcription_key(tmp_path, identity, monkeypatch, capsys):
    from backend.captions import __main__ as cli

    CaptionPipeline(tmp_path, transcriber=FakeTranscriber(), decoder=lambda *a, **k: (b"fixture-wav", {})).generate(
        **generate_args(identity), execute=True)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.setattr(cli, "load_local_environment", lambda: None)
    source = SimpleNamespace(match_id="cam-1", key="match-1.mp4", source_url="https://test.invalid/match-1.mp4")
    monkeypatch.setattr(cli, "SourceRegistry", SimpleNamespace(from_env=lambda: SimpleNamespace(resolve=lambda: [source])))
    heads = []
    def head(value):
        heads.append(value)
        return identity
    monkeypatch.setattr(cli, "head_identity", head)
    assert cli.main(["--match-id", "cam-1", "--execute", "--track-dir", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "reused" and heads == [source]


def test_ready_track_revalidates_live_source_identity_with_bounded_cache(tmp_path, identity, track):
    (tmp_path / f"cam-1-{identity['digest']}.json").write_text(canonical_json(track), encoding="utf-8")
    clock, calls = [0], []
    current = [identity]
    def checker(key, url):
        calls.append((key, url))
        return current[0]
    service = CaptionService(tmp_path, {"cam-1": {"source_key": "match-1.mp4",
                                               "source_url": "https://test.invalid/match-1.mp4"}},
                             {"cam-1": identity}, identity_checker=checker, now=lambda: clock[0])
    assert service.get("cam-1")["status"] == "ready"
    assert calls == [("match-1.mp4", "https://test.invalid/match-1.mp4")]
    current[0] = "b" * 64
    clock[0] = 299
    assert service.get("cam-1")["status"] == "ready" and len(calls) == 1
    clock[0] = 300
    result = service.get("cam-1")
    assert result["status"] == "source_mismatch" and result["cues"] == [] and len(calls) == 2
    current[0] = None
    clock[0] = 600
    assert service.get("cam-1")["reason"] == "source_identity_verification_unavailable"


def test_missing_track_never_checks_remote_object(tmp_path, identity):
    service = CaptionService(tmp_path, {"cam-1": "match-1.mp4"}, {"cam-1": identity},
                             identity_checker=lambda *a: pytest.fail("missing track must not issue HEAD"))
    assert service.get("cam-1")["reason"] == "missing_track"


def test_live_head_uses_only_headers_and_sanitizes_failure(monkeypatch, identity):
    from backend.captions import service

    calls = []
    class HeadResponse:
        def __init__(self):
            self.headers = {"ETag": '"synthetic-etag"', "Content-Length": "100"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def open_head(request, timeout):
        calls.append((request.get_method(), timeout))
        return HeadResponse()
    monkeypatch.setattr(service, "urlopen", open_head)
    assert service.verify_source_identity("match-1.mp4", "https://test.invalid/match-1.mp4") == identity["digest"]
    assert calls == [("HEAD", 4)]
    def fail(*args, **kwargs):
        raise URLError("PRIVATE_SIGNED_URL")
    monkeypatch.setattr(service, "urlopen", fail)
    assert service.verify_source_identity("match-1.mp4", "https://test.invalid/private") is None


def test_ready_identity_deadline_is_not_renewed_by_cached_get(tmp_path, identity, track):
    (tmp_path / f"cam-1-{identity['digest']}.json").write_text(canonical_json(track), encoding="utf-8")
    clock, wall, checks = [0], [1000], []
    def checker(*args):
        checks.append(True)
        return identity
    service = CaptionService(tmp_path, {"cam-1": "match-1.mp4"}, {"cam-1": identity},
                             identity_checker=checker, now=lambda: clock[0], wall_now=lambda: wall[0])
    first = service.get("cam-1")
    assert first["source_identity_valid_until"] == 1300
    assert first["source_identity_revalidate_after_seconds"] == 300
    clock[0], wall[0] = 299, 1299
    cached = service.get("cam-1")
    assert cached["source_identity_valid_until"] == first["source_identity_valid_until"]
    assert cached["source_identity_revalidate_after_seconds"] == 1
    assert len(checks) == 1
    clock[0], wall[0] = 300, 1300
    refreshed = service.get("cam-1")
    assert refreshed["source_identity_valid_until"] == 1600 and len(checks) == 2


def test_scribe_word_grouping_preserves_speakers_events_and_exact_boundaries(identity):
    response = {"text": "TEST FIXTURE (applause) OTHER", "words": [
        {"type": "word", "text": "TEST", "start": .1, "end": .4, "speaker_id": "speaker_0"},
        {"type": "spacing", "text": " ", "start": .4, "end": .5},
        {"type": "word", "text": "FIXTURE", "start": .5, "end": .9, "speaker_id": "speaker_0"},
        {"type": "audio_event", "text": "(applause)", "start": 1, "end": 2},
        {"type": "word", "text": "OTHER", "start": 1.2, "end": 1.6, "speaker_id": "speaker_1"}]}
    result = words_to_track(response, match_id="cam-1", source_key="match-1.mp4", identity=identity["digest"],
                            start=120, end=150, language="en", audio_metadata={})
    assert [cue["text"] for cue in result["cues"]] == ["TEST FIXTURE", "(applause)", "OTHER"]
    assert result["cues"][0]["start_seconds"] == 120.1 and result["cues"][0]["end_seconds"] == 120.9
    assert result["cues"][1]["kind"] == "audio_event" and result["cues"][2]["speaker_id"] == "speaker_1"
    assert result["provenance"]["provider"] == "elevenlabs" and result["provenance"]["timestamp_method"] == "provider_word"


def test_account_check_uses_read_only_sdk_and_returns_no_private_account_fields():
    requests = []
    def get(**kwargs):
        requests.append(kwargs)
        return {"tier": "free", "status": "active", "character_count": 100, "character_limit": 10000,
                "max_credit_limit_extension": 0, "email": "PRIVATE_ACCOUNT"}
    client = SimpleNamespace(user=SimpleNamespace(subscription=SimpleNamespace(get=get)))
    status = ElevenLabsTranscriber("PRIVATE_KEY", client=client).account_status()
    assert status["remaining_credits"] == 9900 and status["scoped_key_quota_verified"] is False
    assert "PRIVATE" not in json.dumps(status)
    assert requests == [{"request_options": {"max_retries": 0, "timeout_in_seconds": 10}}]


def test_realtime_access_check_discards_token_without_transcription():
    requests = []
    def create(token_type, **kwargs):
        requests.append((token_type, kwargs))
        return {"token": "PRIVATE_EPHEMERAL_TOKEN"}
    client = SimpleNamespace(tokens=SimpleNamespace(single_use=SimpleNamespace(create=create)))
    result = ElevenLabsTranscriber("PRIVATE_KEY", client=client).realtime_access_check()
    assert result["status"] == "available" and result["transcription_started"] is False
    assert result["check"] == "ephemeral_token_minted_and_discarded"
    assert "PRIVATE" not in json.dumps(result) and "token" not in result
    assert requests == [("realtime_scribe", {"request_options": {"max_retries": 0, "timeout_in_seconds": 10}})]


@pytest.mark.parametrize("status,detail,code", [
    (401, {"status": "missing_permissions", "message": "PRIVATE_KEY missing speech_to_text"},
     "provider_permission_speech_to_text_missing"),
    (403, {"status": "missing_permissions", "message": "PRIVATE_KEY missing speech_to_text"},
     "provider_permission_speech_to_text_missing"),
    (401, {"status": "missing_permissions", "message": "PRIVATE_KEY missing voices_read"}, "provider_http_401"),
    (401, {"status": "invalid_api_key", "message": "PRIVATE_KEY speech_to_text"}, "provider_http_401"),
    (429, {"status": "missing_permissions", "message": "PRIVATE_KEY speech_to_text"}, "provider_http_429"),
])
def test_realtime_access_check_classifies_only_known_permission_errors(status, detail, code):
    class SDKError(Exception):
        def __init__(self):
            self.status_code, self.body = status, {"detail": detail}
            super().__init__("PRIVATE_ERROR_TEXT")
    def create(*args, **kwargs):
        raise SDKError()
    client = SimpleNamespace(tokens=SimpleNamespace(single_use=SimpleNamespace(create=create)))
    with pytest.raises(CaptionError, match=f"^{code}$"):
        ElevenLabsTranscriber("PRIVATE_KEY", client=client).realtime_access_check()


def test_realtime_access_check_rejects_empty_token_response():
    client = SimpleNamespace(tokens=SimpleNamespace(single_use=SimpleNamespace(create=lambda *a, **k: {"token": ""})))
    with pytest.raises(CaptionError, match="^provider_token_response_invalid$"):
        ElevenLabsTranscriber("PRIVATE_KEY", client=client).realtime_access_check()


def test_realtime_access_cli_emits_only_sanitized_result(monkeypatch, capsys):
    from backend.captions import __main__ as cli

    monkeypatch.setattr(cli, "load_local_environment", lambda: None)
    monkeypatch.setattr(cli, "SourceRegistry", SimpleNamespace(from_env=lambda: pytest.fail("credential check must not resolve media")))
    class Provider:
        def realtime_access_check(self):
            return {"status": "available", "transcription_started": False}
    monkeypatch.setattr(cli, "ElevenLabsTranscriber", Provider)
    assert cli.main(["--realtime-access-check"]) == 0
    assert json.loads(capsys.readouterr().out) == {"status": "available", "transcription_started": False}
    class MissingPermission:
        def realtime_access_check(self):
            raise CaptionError("provider_permission_speech_to_text_missing")
    monkeypatch.setattr(cli, "ElevenLabsTranscriber", MissingPermission)
    assert cli.main(["--realtime-access-check"]) == 2
    assert json.loads(capsys.readouterr().out) == {
        "status": "unavailable", "reason": "provider_permission_speech_to_text_missing"}
