import { useCallback, useEffect, useRef, useState } from 'react';
import './App.css';
import { FEEDS } from './feeds';
import VideoTile from './components/VideoTile';
import { Activity, ArrowUpRight, Check, Moon, Pause, Play, Shuffle, Sun } from 'lucide-react';
import MainPlayer from './components/MainPlayer';
import { withViewTransition } from './viewTransition';
import useBackendSocket from './useBackendSocket';
import { isUnavailableFallback, readSession, validRecommendation } from './replayProtocol';
import { DIRECTOR_MODES, MODE_STORAGE_KEY, preferredMode, readDirector } from './director';
import DirectorPanel from './components/DirectorPanel';
import SessionMoments from './components/SessionMoments';
import HowItWorks from './components/HowItWorks';

// After a manual pick, ignore the backend's switches for this long.
export const MANUAL_HOLD_MS = 30000;

const CONNECTION_LABELS = { connecting: 'Connecting', connected: 'Connected', offline: 'Offline' };

function App() {
  const [feeds, setFeeds] = useState(FEEDS);
  const [sessionState, setSessionState] = useState(null);
  const [backendError, setBackendError] = useState('');
  const [director, setDirector] = useState(null);
  const [pendingMode, setPendingMode] = useState(null);
  const [modeNotice, setModeNotice] = useState('');
  const [activePage, setActivePage] = useState('watch');
  const [selectionKind, setSelectionKind] = useState('initial');
  const [uiNow, setUiNow] = useState(Date.now());
  const [focusedId, setFocusedId] = useState(FEEDS[0].id);
  const [previewsPaused, setPreviewsPaused] = useState(false);
  const [autoSwitch, setAutoSwitch] = useState(true);
  const [holdUntil, setHoldUntil] = useState(0);
  const [seekTo, setSeekTo] = useState(null);
  const [announcement, setAnnouncement] = useState('');
  const [theme, setTheme] = useState(() => {
    try { return localStorage.getItem('match-switcher-theme') === 'light' ? 'light' : 'dark'; }
    catch { return 'dark'; }
  });
  const clock = useRef({ time: 0, playing: true, rate: 1, muted: false, volume: 1, stalled: true, available: true });
  const send = useRef(() => false);
  const session = useRef(null);
  const feedsRef = useRef(feeds);
  const focusedRef = useRef(focusedId);
  const autoRef = useRef(autoSwitch);
  const holdRef = useRef(holdUntil);
  const dirtyControls = useRef({ auto: false, select: false });
  const unavailable = useRef(new Set());
  const latestRecommendation = useRef(null);
  const transition = useRef(0);
  const pendingSelection = useRef(null);
  const pendingAck = useRef(null);
  const directorRef = useRef(null);
  const headingRef = useRef(null);
  const previousId = useRef(focusedId);
  const switchSource = useRef('user');
  const synced = useRef(false);
  const modePreference = useRef(preferredMode(null));
  const pendingModeRef = useRef(null);
  const modeRequestSession = useRef(null);
  const serverSkew = useRef(0);
  const focused = feeds.find((feed) => feed.id === focusedId) || feeds[0];
  feedsRef.current = feeds;
  focusedRef.current = focused.id;
  autoRef.current = autoSwitch;
  holdRef.current = holdUntil;

  const reportPlayback = useCallback(() => {
    clock.current.sample?.();
    const current = session.current;
    const feed = feedsRef.current.find((item) => item.id === focusedRef.current);
    if (!current || current.controls_enabled === false || !feed) return;
    send.current({
      type: 'playback', session_id: current.session_id, match_id: feed.cameraId,
      position: clock.current.time, playing: clock.current.playing, rate: clock.current.rate,
      stalled: Boolean(clock.current.stalled), available: clock.current.available !== false,
      ended: Boolean(clock.current.ended),
    });
  }, []);

  useEffect(() => {
    const timer = setInterval(reportPlayback, 250);
    return () => clearInterval(timer);
  }, [reportPlayback]);

  useEffect(() => {
    const timer = setInterval(() => setUiNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!announcement) return undefined;
    const timer = setTimeout(() => setAnnouncement(''), 4500);
    return () => clearTimeout(timer);
  }, [announcement]);

  useEffect(() => {
    if (!pendingMode) return undefined;
    const timer = setTimeout(() => {
      pendingModeRef.current = null;
      setPendingMode(null);
      setModeNotice('The mode change was not confirmed. Please try again.');
    }, 8000);
    return () => clearTimeout(timer);
  }, [pendingMode]);

  const updateDirector = (value, registered) => {
    const next = readDirector(value, registered);
    if (!next) return null;
    if (directorRef.current && directorRef.current.mode !== next.mode && pendingSelection.current?.source === 'auto') {
      transition.current += 1;
      pendingSelection.current = null;
      pendingAck.current = null;
    }
    if (directorRef.current && directorRef.current.mode !== next.mode) pendingAck.current = null;
    directorRef.current = next;
    setDirector(next);
    if (pendingModeRef.current === next.mode) {
      pendingModeRef.current = null;
      modePreference.current = next.mode;
      setPendingMode(null);
      setModeNotice('');
      try { localStorage.setItem(MODE_STORAGE_KEY, next.mode); } catch {}
    }
    return next;
  };

  const requestMode = (mode) => {
    if (!Object.hasOwn(DIRECTOR_MODES, mode)) return;
    pendingAck.current = null;
    if (pendingSelection.current?.source === 'auto') {
      transition.current += 1;
      pendingSelection.current = null;
      pendingAck.current = null;
    }
    const current = session.current;
    if (!current || current.controls_enabled === false || !send.current({ type: 'director_mode', session_id: current.session_id, mode })) {
      setModeNotice(current?.controls_enabled === false ? 'This replay is controlled by another viewer.' : 'Connect to the director to change mode.');
      return;
    }
    pendingModeRef.current = mode;
    setPendingMode(mode);
    setModeNotice('');
  };

  const acknowledge = useCallback((recommendation) => {
    const current = session.current;
    if (!current || recommendation.session_id !== current.session_id
      || recommendation.model_version !== current.model_version
      || recommendation.clock_epoch !== current.playback.clock_epoch
      || clock.current.stalled || clock.current.available === false) return;
    send.current({ type: 'ack', session_id: current.session_id, sequence: recommendation.sequence,
      clock_epoch: recommendation.clock_epoch, match_id: recommendation.selected_match_id,
      received_at: Date.now() / 1000 });
  }, []);

  const finishRecommendation = useCallback(() => {
    const recommendation = pendingAck.current;
    const current = session.current;
    const feed = feedsRef.current.find((item) => item.id === focusedRef.current);
    if (!recommendation || !current || feed?.cameraId !== recommendation.selected_match_id
      || clock.current.stalled || clock.current.available === false) return;
    clock.current.sample?.();
    pendingAck.current = null;
    if (!autoRef.current || Date.now() < holdRef.current || !validRecommendation(recommendation,
      { ...current, sequence: recommendation.sequence - 1 }, clock.current)) return;
    acknowledge(recommendation);
    if (recommendation.announce !== false) {
      setAnnouncement(`Switched to ${feed.label}`);
      setSelectionKind('automatic');
    }
  }, [acknowledge]);

  useEffect(() => {
    finishRecommendation();
    reportPlayback();
  }, [focusedId, finishRecommendation, reportPlayback]);

  useEffect(() => {
    try { localStorage.setItem('match-switcher-theme', theme); } catch {}
    document.documentElement.dataset.theme = theme;
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = theme === 'dark' ? '#081122' : '#f4f7fc';
  }, [theme]);

  useEffect(() => {
    // Only the user's own picks move keyboard focus; automatic switches never steal it.
    if (focusedId !== previousId.current && switchSource.current === 'user') headingRef.current?.focus();
    previousId.current = focusedId;
  }, [focusedId]);

  useEffect(() => {
    if (!holdUntil) return undefined;
    const timer = setTimeout(() => { holdRef.current = 0; setHoldUntil(0); }, Math.max(0, holdUntil - Date.now()));
    return () => clearTimeout(timer);
  }, [holdUntil]);

  const switchTo = (id, source = 'user', recommendation = null) => {
    const priorAck = pendingAck.current;
    const request = ++transition.current;
    pendingSelection.current = null;
    pendingAck.current = null;
    if (id === focusedRef.current) {
      if (recommendation) {
        pendingAck.current = { ...recommendation, announce: priorAck?.selected_match_id === recommendation.selected_match_id
          ? priorAck.announce : false };
        finishRecommendation();
      }
      return;
    }
    pendingSelection.current = { id, source };
    withViewTransition(() => {
      if (request !== transition.current) return;
      clock.current.sample?.();
      if (recommendation && (!autoRef.current || Date.now() < holdRef.current
        || !validRecommendation(recommendation, { ...session.current, sequence: recommendation.sequence - 1 }, clock.current))) {
        pendingSelection.current = null;
        return;
      }
      switchSource.current = source;
      focusedRef.current = id;
      pendingSelection.current = null;
      pendingAck.current = recommendation ? { ...recommendation, announce: true } : null;
      setFocusedId(id);
    });
  };

  // A manual pick wins over the backend for MANUAL_HOLD_MS.
  const pick = (id) => {
    const feed = feedsRef.current.find((item) => item.id === id);
    if (!feed) return;
    holdRef.current = Date.now() + MANUAL_HOLD_MS;
    setSelectionKind('manual');
    setHoldUntil(holdRef.current);
    const current = session.current;
    dirtyControls.current.select = !current || current.controls_enabled === false || !send.current({
      type: 'select', session_id: current.session_id, match_id: feed.cameraId,
      manual_hold_seconds: MANUAL_HOLD_MS / 1000,
    });
    switchTo(id);
  };

  const connection = useBackendSocket((message) => {
    if (message.type === 'session') {
      const next = readSession(message, session.current);
      if (!next) return;
      if (session.current && (session.current.session_id !== next.session_id
        || session.current.playback.clock_epoch !== next.playback.clock_epoch)) {
        if (session.current.session_id !== next.session_id || pendingSelection.current?.source === 'auto') {
          transition.current += 1;
          pendingSelection.current = null;
        }
        pendingAck.current = null;
      }
      if (session.current && session.current.session_id !== next.session_id) {
        directorRef.current = null;
        setDirector(null);
      }
      const firstSession = !session.current;
      next.feeds.forEach((feed) => {
        const previous = feedsRef.current.find((item) => item.cameraId === feed.cameraId);
        if (previous?.url !== feed.url) unavailable.current.delete(feed.cameraId);
      });
      session.current = next;
      if (pendingAck.current && !next.feeds.some((feed) => feed.cameraId === pendingAck.current.selected_match_id && feed.healthy)) {
        pendingAck.current = null;
      }
      serverSkew.current = next.server_time - Date.now() / 1000;
      feedsRef.current = next.feeds;
      setFeeds(next.feeds);
      setSessionState(next);
      setBackendError('');
      const nextDirector = updateDirector(next.director, next.feeds);
      if (nextDirector && modeRequestSession.current !== next.session_id && next.controls_enabled !== false) {
        modeRequestSession.current = next.session_id;
        if (modePreference.current && modePreference.current !== nextDirector.mode) requestMode(modePreference.current);
      }
      // Join the shared replay once. Reconnection must not rewind a viewer who
      // has continued to play while the backend was unavailable.
      if (!synced.current) {
        synced.current = true;
        if (clock.current.time <= 0.05 && next.playback.position > 0) {
          setSeekTo({ time: next.playback.position });
        }
      }
      const manualMode = (typeof next.auto_enabled === 'boolean' && !dirtyControls.current.auto) ? !next.auto_enabled : !autoRef.current;
      const preservedId = pendingSelection.current?.id ?? focusedRef.current;
      const preserved = next.feeds.find((feed) => feed.id === preservedId && (feed.healthy || manualMode));
      const selected = next.feeds.find((feed) => feed.cameraId === next.current_match_id && feed.healthy);
      const target = (firstSession && !dirtyControls.current.select ? selected : preserved)
        || preserved || selected || next.feeds.find((feed) => feed.healthy) || next.feeds[0];
      if (target.id !== pendingSelection.current?.id) switchTo(target.id, 'auto');
      if (nextDirector && target.cameraId === next.current_match_id && nextDirector.selection_kind) setSelectionKind(nextDirector.selection_kind);
      if (dirtyControls.current.auto && next.controls_enabled !== false) {
        dirtyControls.current.auto = !send.current({ type: 'auto', session_id: next.session_id, enabled: autoRef.current });
      } else if (typeof next.auto_enabled === 'boolean') {
        autoRef.current = next.auto_enabled;
        setAutoSwitch(next.auto_enabled);
      }
      if (dirtyControls.current.select && next.controls_enabled !== false) {
        dirtyControls.current.select = !send.current({ type: 'select', session_id: next.session_id,
          match_id: target.cameraId, manual_hold_seconds: Math.max(0, (holdRef.current - Date.now()) / 1000) });
      } else if (Number.isFinite(next.manual_hold_until)) {
        holdRef.current = next.manual_hold_until * 1000 > Date.now() ? next.manual_hold_until * 1000 : 0;
        setHoldUntil(holdRef.current);
      }
      reportPlayback();
    } else if (message.type === 'recommendation') {
      clock.current.sample?.();
      // Scores can arrive while the newly selected source is buffering. Consume
      // their identity/order without applying another switch, and retain only
      // the newest matching ACK until the actual target is ready.
      if (!validRecommendation(message, session.current, { ...clock.current, stalled: false })) return;
      session.current = { ...session.current, sequence: message.sequence };
      updateDirector(message.director, session.current.feeds);
      latestRecommendation.current = message;
      if (!autoRef.current || Date.now() < holdRef.current || clock.current.ended) return;
      const target = session.current.feeds.find((feed) => feed.cameraId === message.selected_match_id);
      if (unavailable.current.has(target.cameraId)) return;
      if (clock.current.stalled && !isUnavailableFallback(message, clock.current)) {
        pendingAck.current = pendingAck.current && target.id === focusedRef.current
          ? { ...message, announce: pendingAck.current.announce } : null;
        return;
      }
      switchTo(target.id, 'auto', message);
    } else if (message.type === 'error' && message.code === 'viewer_in_use') {
      if (session.current) session.current.controls_enabled = false;
      setBackendError('Viewing only');
    } else if (message.type === 'error' && message.code === 'invalid_director_mode') {
      pendingModeRef.current = null;
      setPendingMode(null);
      setModeNotice('That mode could not be applied. The current settings are unchanged.');
    }
  }, undefined, send);

  useEffect(() => {
    if (connection !== 'connected') modeRequestSession.current = null;
  }, [connection]);

  const toggleAuto = () => {
    const enabled = !autoRef.current;
    if (!enabled) {
      transition.current += 1;
      pendingSelection.current = null;
      pendingAck.current = null;
    }
    autoRef.current = enabled;
    setAutoSwitch(enabled);
    const current = session.current;
    dirtyControls.current.auto = !current || current.controls_enabled === false
      || !send.current({ type: 'auto', session_id: current.session_id, enabled });
  };

  const onPlayerKey = (event) => {
    if (activePage !== 'watch') return;
    if (event.altKey || event.ctrlKey || event.metaKey || event.target.closest('video')) return;
    // Single-key shortcuts are active only while focus is in the player area.
    const index = Number(event.key) - 1;
    if (Number.isInteger(index) && feeds[index]) pick(feeds[index].id);
    if (event.key === 'Escape') document.querySelector('.filmstrip .tile:not([hidden])[role="button"]')?.focus();
  };

  const held = autoSwitch && holdUntil > 0;
  const autoLabel = !autoSwitch ? 'Auto off' : held ? 'Auto paused' : 'Auto';
  const autoTitle = !autoSwitch ? 'Turn on automatic switching'
    : held ? 'Paused after your pick; resumes shortly. Click to turn off'
      : 'Automatically switching to the most interesting match. Click to turn off';
  const inferenceBuffering = connection === 'connected' && ['waiting', 'starting'].includes(sessionState?.state);
  const inferenceLabel = backendError || (sessionState?.controls_enabled === false ? 'Viewing only'
    : inferenceBuffering ? 'Starting inference'
    : sessionState && connection !== 'connected' ? 'Inference offline'
    : sessionState?.state === 'disabled' ? 'Monitoring off'
      : ['failed', 'error', 'unavailable'].includes(sessionState?.state) ? 'Inference unavailable'
      : sessionState?.mode === 'features_mock' ? 'Mock scores'
        : sessionState?.mode === 'real' ? 'Trained model' : 'No inference session');
  const now = uiNow / 1000 + serverSkew.current;
  const monitoring = connection === 'connected' && ['running', 'degraded'].includes(sessionState?.state);
  const mode = director?.mode || 'balanced';
  const scoreFresh = Boolean(monitoring && director && director.scores_fresh !== false
    && Number.isFinite(director.scores_produced_at) && now - director.scores_produced_at <= 6
    && (!Number.isFinite(director.scores_valid_until) || director.scores_valid_until > now));
  const scores = scoreFresh ? Object.fromEntries(Object.entries(director.latest_scores)
    .filter(([id]) => feeds.some((feed) => feed.cameraId === id && feed.healthy !== false))) : {};
  const navigate = (page) => withViewTransition(() => setActivePage(page));

  return (
    <div className="app" data-theme={theme}>
      <a className="skip-link" href="#matches">Skip to player</a>
      <header className="app-header">
        <a className="brand" href="#watch" onClick={(event) => { event.preventDefault(); navigate('watch'); }} aria-label="MatchPulse home">
          <span className="brand-mark"><Activity size={23} aria-hidden="true" /></span>Match<span className="brand-accent">Pulse</span>
        </a>
        <nav className="main-nav" aria-label="Main navigation">
          {[['watch', 'Watch'], ['moments', 'Moments'], ['how', 'How it works']].map(([id, label]) =>
            <a key={id} href={`#${id}`} aria-current={activePage === id ? 'page' : undefined}
              onClick={(event) => { event.preventDefault(); navigate(id); }}>{label}</a>)}
        </nav>
        <div className="header-actions">
          {connection !== 'disabled' && (
            <span className={`connection connection--${connection}`} role="status" title={`Backend: ${CONNECTION_LABELS[connection]}`}>
              <span className="connection__dot" aria-hidden="true" />
              <span className="connection__label">{CONNECTION_LABELS[connection]}</span>
            </span>
          )}
          <button className="director-toggle" aria-label={autoLabel} aria-pressed={autoSwitch} title={autoTitle}
            onClick={toggleAuto}>
            <Shuffle size={18} aria-hidden="true" />
            <span>Auto Director</span><span className={`toggle-track ${autoSwitch ? 'is-on' : ''}`} aria-hidden="true"><i /></span>
          </button>
          <button className="theme-toggle icon-button" onClick={() => withViewTransition(() => setTheme(theme === 'dark' ? 'light' : 'dark'))}
            aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}>
            {theme === 'dark' ? <Sun size={20} aria-hidden="true" /> : <Moon size={20} aria-hidden="true" />}
          </button>
        </div>
      </header>
      <main id="matches" className="app-content" tabIndex={-1} onKeyDown={onPlayerKey}>
        <section id="watch" className="player-layout" hidden={activePage !== 'watch'} aria-label="Watch matches">
          <div className="watch-intro"><div><p className="eyebrow">YOUR MATCHDAY, REIMAGINED</p>
            <p className="hero-title">All the action. <span>In focus.</span></p>
            <p className="hero-description">Your matches, together. Your director, at your pace.</p></div>
            <div className="session-badges"><span className="replay-badge"><span /> Prerecorded replay</span>
              <span className="inference-mode" role="status">{inferenceLabel}</span></div>
          </div>
          <div className="watch-stage"><div className="player-column">
            <div className="player-heading"><div><p className="eyebrow">NOW WATCHING <span>{focused.cameraId}</span></p>
              <h1 ref={headingRef} tabIndex={-1} style={{ viewTransitionName: 'match-heading' }}>{focused.label}</h1></div>
              <span className={`selection-pill ${selectionKind === 'automatic' ? 'is-automatic' : ''}`}>
                {selectionKind === 'automatic' ? <><Activity size={14} aria-hidden="true" /> MatchPulse selected</>
                  : selectionKind === 'manual' ? <><Check size={14} aria-hidden="true" /> Your selection</> : 'Focused match'}</span>
            </div>
            <MainPlayer feed={focused} clock={clock} seekTo={seekTo} onPlayback={reportPlayback}
          inferenceBuffering={inferenceBuffering}
          onAvailability={(matchId, available) => {
            if (available) { unavailable.current.delete(matchId); finishRecommendation(); }
            else { unavailable.current.add(matchId); pendingAck.current = null; }
          }} />
            <div className="player-context"><span><span className="status-dot" />{autoSwitch ? held ? 'Your pick · Auto resumes after the hold' : `Auto Director · ${DIRECTOR_MODES[mode].label}` : 'Manual mode · you choose the match'}</span>
              <span>{scoreFresh && Number.isFinite(scores[focused.cameraId]) ? `Relative ${sessionState?.mode === 'features_mock' ? 'mock' : 'model'} score ${scores[focused.cameraId].toFixed(3)}` : 'Enjoy the match'}</span>
            </div>
          </div>
          <DirectorPanel director={director} mode={mode} pendingMode={pendingMode} notice={modeNotice} onMode={requestMode}
            enabled={autoSwitch} held={held} holdUntil={holdUntil} now={now} monitoring={monitoring} matchCount={feeds.length}
            monitoredCount={feeds.filter((feed) => feed.healthy !== false).length} starting={inferenceBuffering}
            connected={connection === 'connected'} canControl={sessionState?.controls_enabled !== false} scoreFresh={scoreFresh} />
          </div>
        <div className="strip-toolbar"><div>
          <p className="eyebrow">THE REST OF YOUR MATCHDAY</p><h2>Other matches <span>{Math.max(0, feeds.length - 1)}</span></h2>
          <p>Pick a match. We’ll stay with your choice for 30 seconds.</p></div>
          <button className="icon-button" aria-label={previewsPaused ? 'Resume previews' : 'Pause previews'}
            title={previewsPaused ? 'Resume previews' : 'Pause previews'} aria-pressed={previewsPaused}
            onClick={() => setPreviewsPaused(!previewsPaused)}>
            {previewsPaused ? <Play size={18} aria-hidden="true" /> : <Pause size={18} aria-hidden="true" />}
          </button>
        </div>
        <div className={`filmstrip ${feeds.length <= 3 ? 'filmstrip--compact' : ''}`} role="region" aria-label="Other matches" style={{ '--match-count': Math.max(1, feeds.length - 1) }}>
          {feeds.map((feed) => (
            <VideoTile key={feed.cameraId} feed={feed} hidden={feed.id === focused.id} clock={clock}
              paused={previewsPaused || activePage !== 'watch'} onClick={() => pick(feed.id)}
              score={scores[feed.cameraId]} scoreKind={sessionState?.mode === 'features_mock' ? 'mock' : 'model'}
              monitoring={monitoring} />
          ))}
        </div>
        {feeds.length === 1 && <p className="section-note">This replay has one registered match. More matches will appear when they are available.</p>}
        <p className="section-note">{sessionState ? `${feeds.length} distinct ${feeds.length === 1 ? 'source' : 'sources'} registered for this replay.` : 'Previewing available sources. Connect to a replay for confirmed registrations.'}
          {' '}Scores are relative and experimental, not goal probabilities.</p>
        </section>
        <div id="moments" hidden={activePage !== 'moments'}><SessionMoments director={director} feeds={feeds} now={now}
          sessionId={sessionState?.session_id} onWatch={() => navigate('watch')} /></div>
        <div id="how" hidden={activePage !== 'how'}><HowItWorks onWatch={() => navigate('watch')} /></div>
        {activePage !== 'watch' && <button className="return-to-watch" onClick={() => navigate('watch')}><Play size={15} aria-hidden="true" /> Return to {focused.label} <ArrowUpRight size={15} aria-hidden="true" /></button>}
      </main>
      <footer className="app-footer"><span>MatchPulse <span>·</span> Football, in focus.</span><span>Experimental director. You’re always in control.</span></footer>
      <div className={`selection-toast ${announcement ? 'is-visible' : ''}`} role="status" aria-live="polite">
        {announcement && <><Activity size={18} aria-hidden="true" /><span><strong>MatchPulse selected</strong><span>{announcement}</span></span></>}
      </div>
    </div>
  );
}
export default App;
