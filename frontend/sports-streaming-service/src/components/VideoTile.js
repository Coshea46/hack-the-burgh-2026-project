import { useEffect, useRef, useState } from 'react';
import { getPreviewUrl, getTileFallbackUrl } from '../feeds';
import { boundedTime } from './MainPlayer';

export default function VideoTile({ feed, onClick, paused = false, hidden = false, clock }) {
  const ref = useRef(null);
  const [failed, setFailed] = useState(false);
  const [ready, setReady] = useState(false);
  // Until a match's lightweight preview exists in S3, fall back to its full video.
  const [usingFull, setUsingFull] = useState(false);
  const source = usingFull ? getTileFallbackUrl(feed) : getPreviewUrl(feed);

  // Fade the preview in once it has a frame; reset only when the URL changes.
  useEffect(() => { setReady(ref.current.readyState >= 2); }, [source]);

  useEffect(() => {
    const video = ref.current;
    let cancelled = false;
    setFailed(false);
    video.muted = true;
    const sync = () => {
      if (cancelled) return;
      if (paused || hidden) {
        video.pause();
        return;
      }
      if (video.readyState < 1) return;
      // Seeking restarts a tile's download, so tolerate small drift (and more while it is
      // still buffering) and only jump when the tile is genuinely out of step.
      const buffering = video.readyState < 3;
      if (clock) {
        const target = boundedTime(clock.current.time, video.duration);
        const drift = Math.abs(video.currentTime - target);
        if (!video.seeking && drift > (buffering ? 10 : 2)) video.currentTime = target;
        video.playbackRate = clock.current.rate;
      }
      if (clock?.current.playing === false) video.pause();
      else if (video.paused) video.play()?.catch(() => {});
    };
    video.addEventListener('loadedmetadata', sync);
    sync();
    // Bounded drift correction; never seek every frame.
    const interval = !hidden && !paused ? setInterval(sync, 2000) : undefined;
    return () => {
      cancelled = true;
      clearInterval(interval);
      video.removeEventListener('loadedmetadata', sync);
    };
  }, [source, paused, hidden, clock]);

  return (
    <div className="tile" hidden={hidden} role="button" tabIndex={hidden ? -1 : 0}
      style={{ viewTransitionName: `tile-${feed.id}` }}
      aria-label={feed.label} data-feed-id={feed.id} onClick={onClick}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onClick?.(); }
      }}>
      <div className="tile__media">
        <video ref={ref} aria-hidden="true" tabIndex={-1} src={source} loop playsInline
          preload="metadata" muted className={ready ? 'is-ready' : undefined}
          onLoadedData={() => setReady(true)} onError={() => (usingFull ? setFailed(true) : setUsingFull(true))} />
        {failed && <span className="preview-status">Preview unavailable</span>}
      </div>
      <span className="tile__label">{feed.label}</span>
    </div>
  );
}
