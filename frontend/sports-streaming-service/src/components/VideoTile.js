import { useEffect, useRef, useState } from 'react';
import { getPreviewUrl } from '../feeds';
import { boundedTime } from './MainPlayer';

export default function VideoTile({ feed, onClick, paused = false, hidden = false, clock }) {
  const ref = useRef(null);
  const [failed, setFailed] = useState(false);
  const source = getPreviewUrl(feed);

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
      if (clock) {
        const target = boundedTime(clock.current.time, video.duration);
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
  }, [source, paused, hidden, clock]);

  return (
    <div className="tile" hidden={hidden} role="button" tabIndex={hidden ? -1 : 0}
      aria-label={feed.label} data-feed-id={feed.id} onClick={onClick}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onClick?.(); }
      }}>
      <div className="tile__media">
        <video ref={ref} aria-hidden="true" tabIndex={-1} src={source} loop playsInline
          preload="metadata" muted onError={() => setFailed(true)} />
        {failed && <span className="preview-status">Preview unavailable</span>}
      </div>
      <span className="tile__label">{feed.label}</span>
    </div>
  );
}
