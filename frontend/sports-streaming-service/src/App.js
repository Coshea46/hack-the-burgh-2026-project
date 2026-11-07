import { useEffect, useState } from 'react';
import './App.css';
import { FEEDS } from './feeds';
import FeedGrid from './components/FeedGrid';
import FocusView from './components/FocusView';

function App() {
  // null = grid view. A backend-driven switch can simply call setFocusedId.
  const [focusedId, setFocusedId] = useState(null);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') return setFocusedId(null);
      const n = Number(e.key);
      if (FEEDS.some((f) => f.id === n)) setFocusedId(n);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  return (
    <div className="app">
      <header className="app__header">Match Switcher</header>
      {focusedId == null ? (
        <FeedGrid onPick={setFocusedId} />
      ) : (
        <FocusView
          focusedId={focusedId}
          onPick={setFocusedId}
          onBack={() => setFocusedId(null)}
        />
      )}
    </div>
  );
}

export default App;
