import { ArrowRight, History } from 'lucide-react';
import { ageLabel, replayTime } from '../director';

const KIND_LABELS = { automatic: 'MatchPulse selection', manual: 'Your selection', playback: 'Playback selection', fallback: 'Source recovery' };

export default function SessionMoments({ director, feeds, now, sessionId, onWatch }) {
  const events = director?.history || [];
  const label = (id) => feeds.find((feed) => feed.cameraId === id)?.label || 'Session start';
  return <section className="content-page" aria-labelledby="moments-title">
    <p className="eyebrow">YOUR REPLAY, AT A GLANCE</p>
    <h1 id="moments-title">The moments between matches.</h1>
    <p className="page-lead">A factual record of selections in this replay. A switch is a director decision, not a verified football event.</p>
    {events.length ? <ol className="moments-list">{[...events].reverse().map((event) => <li key={event.id}>
      <div className={`moment-icon moment-icon--${event.kind}`}><History size={18} aria-hidden="true" /></div>
      <div className="moment-body"><span className="moment-kind">{KIND_LABELS[event.kind]}</span>
        <p>{label(event.from_match_id)} <ArrowRight size={15} aria-label="to" /> <strong>{label(event.to_match_id)}</strong></p>
        <span className="moment-meta">Replay {replayTime(event.playback_time)} · {ageLabel(event.selected_at, now)}
          {Number.isFinite(event.score) && ` · Relative score ${event.score.toFixed(3)}`}</span>
      </div>
    </li>)}</ol> : <div className="empty-state"><History size={30} aria-hidden="true" /><h2>Your session starts here.</h2>
      <p>{sessionId ? 'Actual manual and automatic selections will appear here as they happen.' : 'Connect to a replay to see its selection history.'}</p>
      <button className="primary-button" onClick={onWatch}>Back to Watch <ArrowRight size={16} aria-hidden="true" /></button>
    </div>}
    <p className="section-note">History belongs to the active replay session and resets when a new session starts.</p>
  </section>;
}
