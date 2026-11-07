import { flushSync } from 'react-dom';

// Runs a state update inside a View Transition so the browser animates
// between the old and new layout. Falls back to an instant update when the
// API is missing or the user prefers reduced motion.
export function withViewTransition(update) {
  const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  if (typeof document.startViewTransition !== 'function' || reduce) {
    update();
    return;
  }
  document.startViewTransition(() => flushSync(update));
}
