import { FEEDS } from '../feeds';
import VideoTile from './VideoTile';

export default function FeedGrid({ onPick }) {
  return (
    <main className="grid">
      {FEEDS.map((feed) => (
        <VideoTile
          key={feed.id}
          feed={feed}
          shortcut={feed.id}
          onClick={() => onPick(feed.id)}
        />
      ))}
    </main>
  );
}
