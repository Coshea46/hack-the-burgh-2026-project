import { FEEDS } from '../feeds';
import VideoTile from './VideoTile';

export default function FocusView({ focusedId, onPick, onBack }) {
  const focused = FEEDS.find((f) => f.id === focusedId);
  const others = FEEDS.filter((f) => f.id !== focusedId);

  return (
    <main className="focus">
      <div className="strip">
        {others.map((feed) => (
          <VideoTile
            key={feed.id}
            feed={feed}
            shortcut={feed.id}
            onClick={() => onPick(feed.id)}
          />
        ))}
      </div>
      <VideoTile key={focused.id} feed={focused} main />
      <button className="back" onClick={onBack}>
        ← All matches
      </button>
    </main>
  );
}
