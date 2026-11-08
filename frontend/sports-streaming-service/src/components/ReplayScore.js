import { getVideoUrl } from '../feeds';
import useSourcePlayback from '../useSourcePlayback';
import { replayScoreAt } from '../captions';

export default function ReplayScore({ feed, mediaRef, source = getVideoUrl(feed) }) {
  const hasScores = Boolean(feed.metadata?.replay?.score_intervals?.length);
  const time = useSourcePlayback(mediaRef, `${source}\n${feed.cameraId}`, hasScores);
  const score = replayScoreAt(feed, time);
  return <span className="replay-scoreline">{score && <strong aria-label={`Verified replay score ${score}`}>{score}</strong>}
    {feed.metadata?.verification?.identity === 'provisional' && <span className="provisional-label">Opponent unconfirmed</span>}</span>;
}
