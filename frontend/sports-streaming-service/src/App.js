import { useEffect, useRef, useState } from 'react';
import './App.css';
import { FEEDS } from './feeds';
import VideoTile from './components/VideoTile';
import { Moon, Pause, Play, Sun } from 'lucide-react';
import MainPlayer from './components/MainPlayer';

function App() {
  const [focusedId, setFocusedId] = useState(FEEDS[0].id);
  const [previewsPaused, setPreviewsPaused] = useState(false);
  const [theme, setTheme] = useState(() => {
    try { return localStorage.getItem('match-switcher-theme') === 'light' ? 'light' : 'dark'; }
    catch { return 'dark'; }
  });
  const clock = useRef({ time: 0, playing: true, rate: 1, muted: false, volume: 1 });
  const headingRef = useRef(null);
  const previousId = useRef(focusedId);
  const focused = FEEDS.find((feed) => feed.id === focusedId);

  useEffect(() => {
    try { localStorage.setItem('match-switcher-theme', theme); } catch {}
    document.documentElement.dataset.theme = theme;
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = theme === 'dark' ? '#101216' : '#f4f5f7';
  }, [theme]);

  useEffect(() => {
    if (focusedId !== previousId.current) headingRef.current?.focus();
    previousId.current = focusedId;
  }, [focusedId]);

  const onPlayerKey = (event) => {
    if (event.altKey || event.ctrlKey || event.metaKey || event.target.closest('video')) return;
    // Single-key shortcuts are active only while focus is in the player area.
    const id = Number(event.key);
    if (FEEDS.some((feed) => feed.id === id)) setFocusedId(id);
    if (event.key === 'Escape') document.querySelector('.filmstrip .tile:not([hidden])[role="button"]')?.focus();
  };

  return (
    <div className="app" data-theme={theme}>
      <a className="skip-link" href="#matches">Skip to player</a>
      <header className="app-header">
        <span className="brand"><Play size={20} aria-hidden="true" />Match Switcher</span>
        <button className="theme-toggle" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
          aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}>
          {theme === 'dark' ? <Sun size={20} aria-hidden="true" /> : <Moon size={20} aria-hidden="true" />}
          <span>{theme === 'dark' ? 'Light mode' : 'Dark mode'}</span>
        </button>
      </header>
      <main id="matches" className="player-layout" tabIndex={-1} onKeyDown={onPlayerKey}>
        <h1 ref={headingRef} tabIndex={-1}>{focused.label}</h1>
        <MainPlayer feed={focused} clock={clock} />
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
            <VideoTile key={feed.id} feed={feed} hidden={feed.id === focusedId} clock={clock} paused={previewsPaused} onClick={() => setFocusedId(feed.id)} />
          ))}
        </div>
      </main>
    </div>
  );
}
export default App;
