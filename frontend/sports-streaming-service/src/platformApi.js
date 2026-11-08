export const API_URL = (process.env.REACT_APP_API_URL || 'http://127.0.0.1:8031').replace(/\/$/, '');
const cache = new Map();

export function clearApiCache() { cache.forEach((entry) => clearTimeout(entry.timer)); cache.clear(); }

export async function apiGet(path, parameters = {}, refresh = false) {
  const query = new URLSearchParams(Object.entries(parameters).filter(([, value]) => value !== '' && value != null));
  const encoded = query.toString();
  const url = `${API_URL}${path}${encoded ? `?${encoded}` : ''}`;
  const previous = cache.get(url);
  if (!refresh && previous && previous.expires > Date.now()) return previous.promise;
  if (previous) clearTimeout(previous.timer);
  const entry = { expires: Date.now() + 60000 };
  const promise = Promise.resolve().then(async () => {
    if (typeof fetch !== 'function') throw new Error('Football data connection is unavailable.');
    const response = await fetch(url, { headers: { Accept: 'application/json' } });
    const body = await response.json();
    if (!body || typeof body !== 'object' || Array.isArray(body)) throw new Error('The football service returned an invalid response.');
    if (!response.ok && !body.status) throw new Error('Football data could not be loaded. Please try again.');
    if (path === '/api/news') {
      const hardExpiry = Number.isFinite(body.content_expires_at) ? body.content_expires_at * 1000
        : Number.isFinite(body.fetched_at) ? (body.fetched_at + 24 * 60 * 60) * 1000 : entry.expires;
      entry.expires = Math.min(entry.expires, hardExpiry);
    }
    if (path === '/api/captions' && Number.isFinite(body.source_identity_valid_until)) {
      entry.expires = Math.min(entry.expires, body.source_identity_valid_until * 1000);
    }
    // Purge cached metadata even if this topic is no longer the visible page.
    entry.timer = setTimeout(() => { if (cache.get(url) === entry) cache.delete(url); }, Math.max(0, entry.expires - Date.now()));
    return body;
  });
  entry.promise = promise;
  cache.set(url, entry);
  if (cache.size > 64) { const oldest = cache.keys().next().value; clearTimeout(cache.get(oldest).timer); cache.delete(oldest); }
  try { return await promise; } catch (error) { if (cache.get(url) === entry) cache.delete(url); throw error; }
}

export function safeWebUrl(value) {
  try { const url = new URL(value); return url.protocol === 'https:' ? url.href : null; } catch { return null; }
}

export function updatedLabel(timestamp) {
  if (!Number.isFinite(timestamp)) return 'Update time unavailable';
  return `Updated ${new Date(timestamp * 1000).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}`;
}
