import { Activity, ChevronDown, Clock3, SlidersHorizontal } from 'lucide-react';
import { ageLabel, DIRECTOR_MODES } from '../director';

export default function DirectorPanel({ director, mode, pendingMode, notice, onMode, enabled, held,
  holdUntil, now, monitoring, matchCount, monitoredCount, starting, connected, canControl, scoreFresh }) {
  const cooldown = Math.max(0, Math.ceil((director?.auto_cooldown_until || 0) - now));
  const label = DIRECTOR_MODES[mode].label;
  const reason = {
    auto_disabled: 'You choose the view. Score updates continue while playback runs.',
    manual_hold: 'Staying with your selection for the manual hold.',
    current_leading: 'The current match leads the latest comparison.',
    automatic_cooldown: 'Giving this selection time before another automatic switch.',
    confirming_challenger: 'Checking for a consistent challenger before switching.',
    challenger_confirmed: 'A challenger led the required consecutive comparisons.',
    unavailable_fallback: 'The previous monitored source became unavailable.',
    waiting_for_scores: 'Waiting for a complete set of fresh scores.',
    mode_changed: 'The updated mode will guide the next fresh comparison.',
  }[director?.decision_reason];
  return (
    <aside className="director-panel" aria-label="Auto Director settings">
      <div className="panel-icon"><SlidersHorizontal size={20} aria-hidden="true" /></div>
      <p className="eyebrow">YOUR PERSONAL DIRECTOR</p>
      <h2>A little less searching.<br />A lot more football.</h2>
      <p className="panel-description">Set the pace. MatchPulse follows the scores while you enjoy the game.</p>
      <div className="mode-field">
        <label htmlFor="director-mode">Director mode</label>
        <div className="select-wrap">
          <select id="director-mode" value={pendingMode || mode} disabled={!connected || !director || !canControl}
            aria-describedby="director-mode-description" onChange={(event) => onMode(event.target.value)}>
            {Object.entries(DIRECTOR_MODES).map(([id, item]) => <option key={id} value={id}>{item.label}</option>)}
          </select>
          <ChevronDown size={17} aria-hidden="true" />
        </div>
        <p id="director-mode-description">{DIRECTOR_MODES[pendingMode || mode].description}</p>
        {pendingMode && <p className="mode-notice" role="status">Applying {DIRECTOR_MODES[pendingMode].label}…</p>}
        {notice && <p className="mode-notice" role="status">{notice}</p>}
      </div>
      {director?.config && <div className="director-rules" aria-label="Applied director settings">
        <span><strong>{director.config.cooldown_seconds}s</strong> between auto switches</span>
        <span><strong>{director.config.confirmations_required}</strong> consistent score {director.config.confirmations_required === 1 ? 'check' : 'checks'}</span>
      </div>}
      <div className="director-state">
        <Activity size={16} aria-hidden="true" />
        <span>{!connected ? 'Director offline' : starting ? `Preparing ${matchCount} matches`
          : monitoring ? `Monitoring ${monitoredCount === matchCount ? matchCount : `${monitoredCount} of ${matchCount}`} ${matchCount === 1 ? 'match' : 'matches'}`
            : 'Monitoring paused or off'}</span>
      </div>
      <div className="director-detail">
        <span>Auto Director</span><strong>{!enabled ? 'Manual' : held ? 'Following your pick' : label}</strong>
      </div>
      {held && <div className="director-detail"><span>Manual hold</span><strong>{Math.max(0, Math.ceil(holdUntil / 1000 - now))}s remaining</strong></div>}
      {!held && enabled && cooldown > 0 && <div className="director-detail"><span>Switch cooldown</span><strong>{cooldown}s remaining</strong></div>}
      <div className="director-detail"><span>Latest scores</span><strong>{scoreFresh ? ageLabel(director.scores_produced_at, now) : 'Waiting for fresh scores'}</strong></div>
      <div className="director-detail"><span>Last switch</span><strong>{Number.isFinite(director?.last_switch_at) ? ageLabel(director.last_switch_at, now) : 'No switches yet'}</strong></div>
      {reason && <p className="director-reason">{reason}</p>}
      <p className="director-footnote"><Clock3 size={14} aria-hidden="true" /> Scores update about every 2 seconds. Switching follows your mode.</p>
    </aside>
  );
}
