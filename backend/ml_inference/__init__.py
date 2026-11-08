"""Opt-in MatchPulse inference. Importing this package never contacts Modal."""

from .api import select_best_match, select_best_match_video_only
from .config import InferenceConfig
from .scoring import choose_match
from .service import InferenceService

__all__ = ["InferenceConfig", "InferenceService", "choose_match", "select_best_match",
           "select_best_match_video_only"]
