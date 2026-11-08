"""Offline, reusable captions with explicit source identity and real timing."""

from .schema import cue_at, source_identity, validate_track, webvtt
from .service import CaptionService

__all__ = ["CaptionService", "cue_at", "source_identity", "validate_track", "webvtt"]
