import { useEffect, useRef, useState } from 'react';

// docker-compose sets REACT_APP_WS_URL; plain `npm start` falls back to the local backend.
// Set REACT_APP_WS_URL= (empty) to turn the connection off.
export const WS_URL = process.env.REACT_APP_WS_URL ?? 'ws://localhost:8000';

/**
 * Keeps a WebSocket to the backend open, reconnecting with backoff
 * (1s, 2s, 4s ... up to 30s). Calls onMessage with each parsed JSON message.
 * Returns 'connecting' | 'connected' | 'offline' | 'disabled'.
 */
export default function useBackendSocket(onMessage, url = WS_URL) {
  const [status, setStatus] = useState(url ? 'connecting' : 'disabled');
  const handler = useRef(onMessage);
  useEffect(() => { handler.current = onMessage; });

  useEffect(() => {
    if (!url || typeof WebSocket === 'undefined') {
      setStatus('disabled');
      return undefined;
    }
    let socket;
    let retryTimer;
    let attempts = 0;

    const connect = () => {
      if (attempts === 0) setStatus('connecting');
      socket = new WebSocket(url);
      socket.onopen = () => {
        attempts = 0;
        setStatus('connected');
      };
      socket.onmessage = (event) => {
        let message;
        try { message = JSON.parse(event.data); } catch { return; }
        if (message && typeof message.type === 'string') handler.current(message);
      };
      // onerror is always followed by onclose, so retrying here covers both.
      socket.onclose = () => {
        setStatus('offline');
        retryTimer = setTimeout(connect, Math.min(30000, 1000 * 2 ** attempts++));
      };
    };

    connect();
    return () => {
      clearTimeout(retryTimer);
      socket.onclose = null;
      socket.close();
    };
  }, [url]);

  return status;
}
