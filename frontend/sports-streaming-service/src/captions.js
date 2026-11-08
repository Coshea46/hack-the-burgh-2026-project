export function readCaptionTrack(value, feed) {
  if (value?.status !== 'ready' || value.match_id !== feed.cameraId || value.source_key !== feed.sourceKey
    || (feed.sourceIdentity && value.source_identity !== feed.sourceIdentity) || !Array.isArray(value.cues)
    || value.timing_accuracy !== 'provider_word' || value.provenance?.provider !== 'elevenlabs'
    || value.provenance.model !== 'scribe_v2' || value.provenance.timestamp_method !== 'provider_word'
    || value.provenance.machine_generated !== true) return null;
  const seen = new Set();
  const cues = value.cues.filter((cue) => {
    if (!Number.isFinite(cue.start_seconds) || !Number.isFinite(cue.end_seconds) || cue.start_seconds < 0
      || cue.end_seconds <= cue.start_seconds || typeof cue.text !== 'string' || !cue.text.trim()) return false;
    const key = `${cue.start_seconds}:${cue.end_seconds}:${cue.kind || ''}:${cue.speaker_id || ''}:${cue.text}`;
    if (seen.has(key)) return false;
    seen.add(key); return true;
  }).sort((a, b) => a.start_seconds - b.start_seconds || a.end_seconds - b.end_seconds);
  return { ...value, cues };
}

export function captionAt(track, sourceTime) {
  if (!track || !Number.isFinite(sourceTime)) return '';
  return [...new Set(track.cues.filter((cue) => cue.start_seconds <= sourceTime && sourceTime < cue.end_seconds)
    .map((cue) => {
      const speaker = cue.kind !== 'audio_event' && /^speaker_(\d{1,3})$/.exec(cue.speaker_id || '');
      return `${speaker ? `Speaker ${Number(speaker[1]) + 1}: ` : ''}${cue.text.trim()}`;
    }))].slice(0, 3).join('\n');
}

export function replayScoreAt(feed, sourceTime) {
  if (!Number.isFinite(sourceTime)) return null;
  const interval = feed.metadata?.replay?.score_intervals?.find((item) => item.verified === true
    && Number.isFinite(item.start_seconds) && Number.isFinite(item.end_seconds)
    && item.start_seconds <= sourceTime && sourceTime < item.end_seconds
    && Number.isInteger(item.home) && item.home >= 0 && Number.isInteger(item.away) && item.away >= 0);
  return interval ? `${interval.home}–${interval.away}` : null;
}
