import { useEffect, useRef, useState } from 'react';
import { getPreviewUrl, getVideoUrl, sourceOffset } from '../feeds';
import { boundedTime } from './MainPlayer';

export default function VideoTile({ feed, onClick, paused = false, hidden = false, clock, score, scoreKind = 'model', monitoring = false }) {
  const ref = useRef(null);
  const [failed, setFailed] = useState(false);
  const [ready, setReady] = useState(false);
  // Until a match's lightweight preview exists in S3, fall back to its full video.
  const [usingFull, setUsingFull] = useState(false);
  const source = usingFull ? getVideoUrl(feed) : getPreviewUrl(feed);
  const offset = sourceOffset(feed);

  // Fade the preview in once it has a frame; reset only when the URL changes.
  useEffect(() => { setReady(ref.current.readyState >= 2); setFailed(false); }, [source]);

  useEffect(() => {
    const video = ref.current;
    let cancelled = false;
    video.muted = true;
    const sync = () => {
      if (cancelled) return;
      if (paused || hidden) {
        video.pause();
        return;
      }
      if (video.readyState < 1) return;
      if (clock) {
        if (Number.isFinite(video.duration) && clock.current.time + offset >= video.duration) {
          video.pause();
          return;
        }
        const target = boundedTime(clock.current.time + offset, video.duration);
        if (!video.seeking && Math.abs(video.currentTime - target) > 0.75) video.currentTime = target;
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
  }, [source, paused, hidden, clock, offset, feed.healthy]);

  return (
    <div className="tile" hidden={hidden} role="button" tabIndex={hidden ? -1 : 0}
      style={{ viewTransitionName: `tile-${feed.id}` }}
      aria-label={feed.healthy === false ? `${feed.label} (monitoring unavailable)` : feed.label}
      data-feed-id={feed.id} onClick={onClick}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onClick?.(); }
      }}>
      <div className="tile__media"><span className="preview-id">{feed.cameraId}</span>
        <video ref={ref} aria-hidden="true" tabIndex={-1} src={source} playsInline
          preload="metadata" muted className={ready ? 'is-ready' : undefined}
          onLoadedData={() => setReady(true)} onError={() => (usingFull ? setFailed(true) : setUsingFull(true))} />
        {failed && <span className="preview-status">Preview unavailable</span>}
      </div>
      <span className="tile__label"><span className="tile__name">{feed.label}<span aria-hidden="true">↗</span></span>
        <span className="tile__details"><span className={monitoring && feed.healthy !== false ? 'is-monitoring' : ''}>
          <i aria-hidden="true" />{feed.healthy === false ? 'Monitoring unavailable' : monitoring ? 'Monitoring' : 'Replay source'}</span>
          {Number.isFinite(score) && <span className="relative-score" title={`Relative ${scoreKind} score; not a goal probability`}>{scoreKind === 'mock' ? 'Mock' : 'Score'} {score.toFixed(3)}</span>}
        </span>
      </span>
    </div>
  );
}
