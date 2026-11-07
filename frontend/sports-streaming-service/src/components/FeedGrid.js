import { FEEDS } from '../feeds';
import VideoTile from './VideoTile';

export default function FeedGrid({ onPick, previewsPaused }) {
  return (
    <main id="matches" className="grid" aria-label="All matches" tabIndex={-1}>
      {FEEDS.map((feed) => (
        <VideoTile
          key={feed.id}
          feed={feed}
          shortcut={feed.id} paused={previewsPaused}
          onClick={() => onPick(feed.id)}
        />
      ))}
    </main>
  );
}
