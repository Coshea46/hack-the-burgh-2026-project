"""Interchangeable mock and research portable-bundle adapters."""

from pathlib import Path
from threading import Lock
from typing import Protocol

import numpy as np

from .config import SCHEMA_VERSION, finite_number
from .validation import validate_features, validate_match_id


class InterestScorer(Protocol):
    def predict_scores(self, features: dict[str, np.ndarray]) -> dict[str, float]: ...


def validate_scores(scores, expected_ids):
    if not isinstance(scores, dict) or set(scores) != set(expected_ids):
        raise ValueError("Classifier must return exactly one score per supplied match ID")
    result = {}
    for match_id, score in scores.items():
        value = finite_number(score, "interest score")
        if value > 1:
            raise ValueError("Interest score must lie in [0,1]")
        result[match_id] = value
    return result


class MockInterestScorer:
    """EXPLICIT MOCK: synthetic constant/configured scores, no predictive meaning."""

    def __init__(self, scores=None, *, default_score=0.5):
        self.scores = dict(scores or {})
        self.default_score = default_score
        validate_scores({"default": default_score}, ["default"])
        for match_id in self.scores:
            validate_match_id(match_id)
        validate_scores(self.scores, self.scores)

    def score_ids(self, match_ids):
        return validate_scores(
            {key: self.scores.get(key, self.default_score) for key in match_ids}, match_ids
        )

    def predict_scores(self, features):
        for value in features.values():
            validate_features(value)
        return self.score_ids(list(features))


class ResearchInterestScorer:
    """Load the real research export; delegate normalization/selection/batching unchanged.

    This adapter runs inside the compatible worker environment (Python >=3.11).
    loader injection supports local tests without Torch or a trained checkpoint.
    """

    def __init__(self, checkpoint, *, device="cpu", loader=None):
        self.path = Path(checkpoint)
        self.device, self.loader = device, loader
        self._classifier = None
        self._lock = Lock()

    def prepare(self):
        with self._lock:
            if self._classifier is None:
                if not self.path.is_file():
                    raise FileNotFoundError(f"Portable classifier bundle does not exist: {self.path}")
                loader = self.loader
                if loader is None:
                    from matchpulse import load_interest_classifier

                    loader = load_interest_classifier
                classifier = loader(self.path, device=self.device)
                metadata = classifier.metadata
                if (metadata.get("feature_schema_version") != SCHEMA_VERSION
                        or metadata.get("input_shape") != [75, 215]
                        or metadata.get("sampling_fps") != 15
                        or metadata.get("clip_duration_seconds") != 5):
                    raise ValueError("Classifier does not implement the five-second MatchPulse schema")
                if (metadata.get("model_input_size") != 215
                        or metadata.get("feature_indices") != list(range(215))):
                    raise ValueError("Production requires a full-audio 215-channel classifier bundle")
                self._classifier = classifier
        return self

    def predict_scores(self, features):
        for match_id, value in features.items():
            validate_match_id(match_id)
            validate_features(value, missing_audio=False)
        self.prepare()
        ids = sorted(features)
        if not ids:
            return {}
        # Raw tensors go straight to the research API. It owns saved normalization,
        # 215/210 channel selection, model.eval(), inference_mode() and sigmoid.
        scores = np.asarray(self._classifier.predict_batch(np.stack([features[key] for key in ids])))
        if scores.shape != (len(ids),):
            raise ValueError("Research classifier returned an invalid batch dimension")
        return validate_scores(dict(zip(ids, scores)), ids)
