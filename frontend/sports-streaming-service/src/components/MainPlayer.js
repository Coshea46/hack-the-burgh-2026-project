import { useEffect, useRef, useState } from 'react';
import { getVideoUrl } from '../feeds';

export function boundedTime(time, duration) {
  const safe = Number.isFinite(time) ? Math.max(0, time) : 0;
  return Number.isFinite(duration) ? Math.min(safe, Math.max(0, duration - 0.1)) : safe;
}

// The DOM element survives every selection. Only a genuinely different URL loads.
export default function MainPlayer({ feed, clock, seekTo }) {
  const ref = useRef(null);
  const source = getVideoUrl(feed);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    const video = ref.current;
    let cancelled = false;
    let preparing = true;
    const target = { ...clock.current };
    setLoading(true);
    setError(false);

    const remember = () => {
      if (preparing) return;
      clock.current.time = video.currentTime;
      clock.current.rate = video.playbackRate;
      clock.current.muted = video.muted;
      clock.current.volume = video.volume;
    };
    const fail = () => {
      if (cancelled) return;
      setError(true);
      setLoading(false);
    };
    const ready = () => {
      if (cancelled || !preparing || video.seeking || video.readyState < 2) return;
      preparing = false;
      setLoading(false);
      remember();
      if (target.playing) {
        const attempt = video.play();
        if (attempt?.catch) attempt.catch((reason) => {
          if (cancelled || reason?.name === 'AbortError') return;
          if (reason?.name === 'NotAllowedError') {
            video.muted = true;
            clock.current.muted = true;
            video.play()?.catch(() => { if (!cancelled) clock.current.playing = false; });
          } else fail();
        });
      }
    };
    const metadata = () => {
      if (cancelled) return;
      video.playbackRate = target.rate;
      video.volume = target.volume;
      video.muted = target.muted;
      const time = boundedTime(target.time, video.duration);
      clock.current.time = time;
      if (Math.abs(video.currentTime - time) > 0.05) video.currentTime = time;
      ready();
    };
    const playing = () => { if (!preparing) clock.current.playing = true; };
    const paused = () => { if (!preparing) { remember(); clock.current.playing = false; } };
    const listeners = {
      loadedmetadata: metadata, canplay: ready, seeked: ready, error: fail,
      timeupdate: remember, seeking: remember, ratechange: remember,
      volumechange: remember, play: playing, pause: paused,
    };
    Object.entries(listeners).forEach(([event, handler]) => video.addEventListener(event, handler));
    // Set src imperatively after saving the old timeline, rather than letting a
    // React src mutation reset currentTime before the handoff can capture it.
    if (video.getAttribute('src') !== source) video.src = source;
    else if (retry) video.load();
    else if (video.readyState >= 1) metadata();

    return () => {
      remember();
      cancelled = true;
      Object.entries(listeners).forEach(([event, handler]) => video.removeEventListener(event, handler));
    };
  }, [source, clock, retry]);

  // External seek (the backend's live timestamp). Declared after the effect above
  // so its metadata listener runs last and wins. Previews follow via the shared clock.
  useEffect(() => {
    if (!seekTo) return undefined;
    const video = ref.current;
    clock.current.time = seekTo.time;
    const apply = () => { video.currentTime = boundedTime(seekTo.time, video.duration); };
    if (video.readyState >= 1) {
      apply();
      return undefined;
    }
    video.addEventListener('loadedmetadata', apply, { once: true });
    return () => video.removeEventListener('loadedmetadata', apply);
  }, [seekTo, clock]);

  return (
    <div className="tile tile--main" aria-busy={loading} style={{ viewTransitionName: 'main-player' }}>
      <div className="tile__media">
        <video ref={ref} aria-label={feed.label + ' video'} controls loop playsInline preload="auto" />
        <span className={`player-status ${loading ? 'is-visible' : ''}`} role="status">{loading ? 'Loading match...' : ''}</span>
        {error && <div className="player-error" role="alert">
          <span>Video unavailable.</span>
          <button className="theme-toggle" onClick={() => setRetry((value) => value + 1)}>Retry</button>
        </div>}
      </div>
    </div>
  );
}
