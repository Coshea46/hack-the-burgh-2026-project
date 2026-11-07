import { FEEDS } from '../feeds';
import VideoTile from './VideoTile';

export default function FocusView({ focusedId, onPick, onBack, previewsPaused }) {
  const focused = FEEDS.find((f) => f.id === focusedId);
  const others = FEEDS.filter((f) => f.id !== focusedId);

  return (
    <main id="matches" className="focus" aria-label="Focused match" tabIndex={-1}>
      <div className="focus__player">
        <VideoTile key={focused.id} feed={focused} main />
        <button className="back" onClick={onBack}>{'\u2190 All matches'}</button>
      </div>
      <section className="focus__others" aria-labelledby="other-matches">
        <div className="section-heading"><h2 id="other-matches">Other matches</h2><span>{others.length} feeds</span></div>
        <div className="strip">
          {others.map((feed) => <VideoTile key={feed.id} feed={feed} shortcut={feed.id} paused={previewsPaused} onClick={() => onPick(feed.id)} />)}
        </div>
      </section>
    </main>
  );
}
