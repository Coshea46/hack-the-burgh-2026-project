import { ArrowRight, Eye, Hand, Layers3, Radio, Sparkles } from 'lucide-react';

const STEPS = [
  [Layers3, 'One place. Every match.', 'Follow the registered matches together, with one focused player and synchronized alternatives.'],
  [Eye, 'A fresh look, every few seconds.', 'Computer vision and machine learning examine the preceding five seconds of video and audio.'],
  [Sparkles, 'An experimental interest score.', 'The model compares which match may become interesting. Its scores are relative and are not goal probabilities.'],
  [Radio, 'A director with a little patience.', 'Your chosen mode sets the switching pace. Fresh, consistent scores help the director choose when to move.'],
  [Hand, 'You always have the final say.', 'Pick a match to hold it for 30 seconds, or turn Auto off. Monitoring can continue while you stay in control.'],
];

export default function HowItWorks({ onWatch }) {
  return <section className="content-page" aria-labelledby="how-title">
    <p className="eyebrow">MORE FOOTBALL. LESS CHANNEL HOPPING.</p>
    <h1 id="how-title">A thoughtful way to follow the action.</h1>
    <p className="page-lead">MatchPulse brings several games into one viewing experience, with an experimental director that helps you choose what to watch.</p>
    <div className="how-grid">{STEPS.map(([Icon, title, description], index) => <article key={title} className="how-card">
      <span className="how-number">0{index + 1}</span><Icon size={24} aria-hidden="true" /><h2>{title}</h2><p>{description}</p>
    </article>)}</div>
    <div className="honesty-note"><div><strong>A replay, with real limitations.</strong>
      <p>This demo uses prerecorded football footage. The model is experimental, prediction accuracy is not guaranteed, and a selection does not mean a goal is coming.</p></div>
      <button className="primary-button" onClick={onWatch}>Start watching <ArrowRight size={16} aria-hidden="true" /></button>
    </div>
  </section>;
}
