from types import SimpleNamespace

import numpy as np
import pytest

from backend.ml_inference.classifiers import MockInterestScorer, ResearchInterestScorer


def features(value=0.25):
    x = np.zeros((75, 215), np.float32)
    x[:, 0] = value
    x[:, 214] = 1
    return x


def metadata():
    return {"feature_schema_version": "matchpulse-215-v1", "input_shape": [75, 215],
            "sampling_fps": 15, "clip_duration_seconds": 5,
            "model_input_size": 215, "feature_indices": list(range(215))}


def test_mock_deterministic_configured_and_default():
    mock = MockInterestScorer({"b": 0.9})
    assert mock.predict_scores({"a": features(), "b": features()}) == {"a": 0.5, "b": 0.9}
    assert mock.score_ids(["a", "b"]) == mock.score_ids(["a", "b"])


def test_missing_real_bundle_fails_before_importing_torch(tmp_path):
    adapter = ResearchInterestScorer(tmp_path / "missing.pt")
    with pytest.raises(FileNotFoundError, match="Portable classifier bundle"):
        adapter.predict_scores({"a": features()})


@pytest.mark.parametrize("input_size", [210, 215])
def test_real_adapter_delegates_saved_preprocessing_and_batch_selection(tmp_path, input_size):
    path = tmp_path / "classifier.pt"
    path.write_bytes(b"synthetic loader fixture, not an actual Torch bundle")
    loads, raw_calls, prepared = [], [], []

    info = metadata()
    info.update(model_input_size=input_size, feature_indices=list(range(input_size)))

    class ResearchAPIFixture:
        metadata = info

        def predict_batch(self, raw):
            # Simulates ownership by the existing portable-bundle API: the adapter
            # must send raw values and let this API apply its saved state exactly once.
            raw_calls.append(raw.copy())
            normalized = raw.copy()
            normalized[..., 0] = (raw[..., 0] - 0.1) / 0.5
            normalized = normalized[..., :input_size]
            prepared.append(normalized)
            return normalized[:, :, 0].mean(axis=1)

    def loader(filename, *, device):
        loads.append((filename, device))
        return ResearchAPIFixture()

    scorer = ResearchInterestScorer(path, loader=loader)
    if input_size == 210:
        with pytest.raises(ValueError, match="full-audio"):
            scorer.prepare()
        return
    result = scorer.predict_scores({"z": features(0.4), "a": features(0.2)})
    assert result["a"] == pytest.approx(0.2)
    assert result["z"] == pytest.approx(0.6)
    assert prepared[0].shape == (2, 75, input_size)
    np.testing.assert_array_equal(raw_calls[0][0], features(0.2))
    scorer.predict_scores({"z": features(0.4)})
    assert loads == [(path, "cpu")]


@pytest.mark.parametrize("field,value", [("input_shape", [75, 210]),
                                        ("sampling_fps", 25),
                                        ("feature_schema_version", "other")])
def test_real_schema_rejected(tmp_path, field, value):
    path = tmp_path / "classifier.pt"
    path.write_bytes(b"fixture")
    info = metadata()
    info[field] = value
    scorer = ResearchInterestScorer(path, loader=lambda *a, **kw: SimpleNamespace(metadata=info))
    with pytest.raises(ValueError, match="schema"):
        scorer.prepare()


@pytest.mark.parametrize("shape,dtype", [((75, 210), np.float32), ((1, 75, 215), np.float32),
                                       ((75, 215), np.float64)])
def test_classifier_feature_validation(shape, dtype, tmp_path):
    scorer = ResearchInterestScorer(tmp_path / "not-required.pt")
    with pytest.raises(ValueError, match="float32"):
        scorer.predict_scores({"a": np.zeros(shape, dtype)})


def test_real_adapter_rejects_bad_batch_result(tmp_path):
    path = tmp_path / "classifier.pt"
    path.write_bytes(b"fixture")
    model = SimpleNamespace(metadata=metadata(), predict_batch=lambda x: np.zeros((len(x), 1)))
    scorer = ResearchInterestScorer(path, loader=lambda *a, **kw: model)
    with pytest.raises(ValueError, match="batch dimension"):
        scorer.predict_scores({"a": features()})
