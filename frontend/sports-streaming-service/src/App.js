import { useEffect, useRef, useState } from 'react';
import './App.css';
import { FEEDS, feedIdFromTarget } from './feeds';
import VideoTile from './components/VideoTile';
import { Moon, Pause, Play, Shuffle, Sun } from 'lucide-react';
import MainPlayer from './components/MainPlayer';
import { withViewTransition } from './viewTransition';
import useBackendSocket from './useBackendSocket';

// After a manual pick, ignore the backend's switches for this long.
export const MANUAL_HOLD_MS = 30000;

const CONNECTION_LABELS = { connecting: 'Connecting', connected: 'Live', offline: 'Offline' };

function App() {
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
  const clock = useRef({ time: 0, playing: true, rate: 1, muted: false, volume: 1 });
  const headingRef = useRef(null);
  const previousId = useRef(focusedId);
  const switchSource = useRef('user');
  const synced = useRef(false);
  const focused = FEEDS.find((feed) => feed.id === focusedId);

  useEffect(() => {
    try { localStorage.setItem('match-switcher-theme', theme); } catch {}
    document.documentElement.dataset.theme = theme;
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = theme === 'dark' ? '#101216' : '#f4f5f7';
  }, [theme]);

  useEffect(() => {
    // Only the user's own picks move keyboard focus; automatic switches never steal it.
    if (focusedId !== previousId.current && switchSource.current === 'user') headingRef.current?.focus();
    previousId.current = focusedId;
  }, [focusedId]);

  useEffect(() => {
    if (!holdUntil) return undefined;
    const timer = setTimeout(() => setHoldUntil(0), Math.max(0, holdUntil - Date.now()));
    return () => clearTimeout(timer);
  }, [holdUntil]);

  const switchTo = (id, source = 'user') => {
    if (id === focusedId) return;
    switchSource.current = source;
    withViewTransition(() => setFocusedId(id));
  };

  // A manual pick wins over the backend for MANUAL_HOLD_MS.
  const pick = (id) => {
    setHoldUntil(Date.now() + MANUAL_HOLD_MS);
    switchTo(id);
  };

  const connection = useBackendSocket((message) => {
    if (message.type === 'sync') {
      // Join at the live point once per page load; a backend restart shouldn't rewind the viewer.
      const time = Number(message.current_live_timestamp);
      if (!synced.current && Number.isFinite(time)) {
        synced.current = true;
        setSeekTo({ time });
      }
    } else if (message.type === 'switch') {
      if (!autoSwitch || Date.now() < holdUntil) return;
      const id = feedIdFromTarget(message.target_feed);
      if (id === null || id === focusedId) return;
      switchTo(id, 'auto');
      setAnnouncement(`Switched to ${FEEDS.find((feed) => feed.id === id).label}`);
    }
  });

  const onPlayerKey = (event) => {
    if (event.altKey || event.ctrlKey || event.metaKey || event.target.closest('video')) return;
    // Single-key shortcuts are active only while focus is in the player area.
    const id = Number(event.key);
    if (FEEDS.some((feed) => feed.id === id)) pick(id);
    if (event.key === 'Escape') document.querySelector('.filmstrip .tile:not([hidden])[role="button"]')?.focus();
  };

  const held = autoSwitch && holdUntil > 0;
  const autoLabel = !autoSwitch ? 'Auto off' : held ? 'Auto paused' : 'Auto';
  const autoTitle = !autoSwitch ? 'Turn on automatic switching'
    : held ? 'Paused after your pick; resumes shortly. Click to turn off'
      : 'Automatically switching to the most interesting match. Click to turn off';

  return (
    <div className="app" data-theme={theme}>
      <a className="skip-link" href="#matches">Skip to player</a>
      <header className="app-header">
        <span className="brand"><Play size={20} aria-hidden="true" />Match Switcher</span>
        <div className="header-actions">
          {connection !== 'disabled' && (
            <span className={`connection connection--${connection}`} role="status" title={`Backend: ${CONNECTION_LABELS[connection]}`}>
              <span className="connection__dot" aria-hidden="true" />
              <span className="connection__label">{CONNECTION_LABELS[connection]}</span>
            </span>
          )}
          <button className="theme-toggle" aria-pressed={autoSwitch} title={autoTitle}
            onClick={() => { setAutoSwitch(!autoSwitch); setHoldUntil(0); }}>
            <Shuffle size={18} aria-hidden="true" />
            <span>{autoLabel}</span>
          </button>
          <button className="theme-toggle" onClick={() => withViewTransition(() => setTheme(theme === 'dark' ? 'light' : 'dark'))}
            aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}>
            {theme === 'dark' ? <Sun size={20} aria-hidden="true" /> : <Moon size={20} aria-hidden="true" />}
            <span>{theme === 'dark' ? 'Light mode' : 'Dark mode'}</span>
          </button>
        </div>
      </header>
      <main id="matches" className="player-layout" tabIndex={-1} onKeyDown={onPlayerKey}>
        <h1 ref={headingRef} tabIndex={-1} style={{ viewTransitionName: 'match-heading' }}>{focused.label}</h1>
        <MainPlayer feed={focused} clock={clock} seekTo={seekTo} />
        <div className="strip-toolbar">
          <h2>Other matches</h2>
          <button className="icon-button" aria-label={previewsPaused ? 'Resume previews' : 'Pause previews'}
            title={previewsPaused ? 'Resume previews' : 'Pause previews'} aria-pressed={previewsPaused}
            onClick={() => setPreviewsPaused(!previewsPaused)}>
            {previewsPaused ? <Play size={18} aria-hidden="true" /> : <Pause size={18} aria-hidden="true" />}
          </button>
        </div>
        <div className="filmstrip" role="region" aria-label="Other matches">
          {FEEDS.map((feed) => (
            <VideoTile key={feed.id} feed={feed} hidden={feed.id === focusedId} clock={clock} paused={previewsPaused} onClick={() => pick(feed.id)} />
          ))}
        </div>
      </main>
      <div className="sr-only" aria-live="polite">{announcement}</div>
    </div>
  );
}
export default App;
