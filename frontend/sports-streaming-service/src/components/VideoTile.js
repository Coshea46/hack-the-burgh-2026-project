import { useEffect, useRef } from 'react';
import { getVideoUrl } from '../feeds';

// main=false: muted looping preview. main=true: unmuted with controls.
export default function VideoTile({ feed, main = false, onClick, shortcut }) {
  const ref = useRef(null);

  useEffect(() => {
    const v = ref.current;
    if (!v) return;
    v.muted = !main;
    const p = v.play();
    if (p && p.catch) {
      // Browsers may block unmuted autoplay; fall back to muted.
      p.catch(() => {
        v.muted = true;
        v.play().catch(() => {});
      });
    }
  }, [main, feed.id]);

  return (
    <div
      className={`tile ${main ? 'tile--main' : ''}`}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={(e) => onClick && e.key === 'Enter' && onClick()}
      aria-label={feed.label}
    >
      <video
        ref={ref}
        src={getVideoUrl(feed)}
        loop
        playsInline
        preload="auto"
        muted={!main}
        controls={main}
        autoPlay
      />
      <span className="tile__label">
        {shortcut && <kbd>{shortcut}</kbd>}
        {feed.label}
      </span>
    </div>
  );
}
