/* A small in-memory stand-in for the account API the favorites use, with the same rules as backend/api/account.py + services/prefs.py
 * (it runs the shared core/prefs.js sanitize/merge, the browser twin of the Python code): GET /auth/me, GET|PUT /auth/prefs
 * (lists are unioned, `remove` takes ids out and `remove.fields` clears area/ptype/sort, a full 30-item list answers 409 saved_limit), GET /auth/csrf. The account is whoever
 * `server.user` is: requests never choose it. Every request is recorded in `server.requests`. */
import { sanitize, merge } from '../../../frontend/js/core/prefs.js';

export function createAccountServer() {
  const server = { user: null, prefs: new Map(), requests: [], failNext: null, holdNext: null };
  const json = (status, body) => ({ ok: status >= 200 && status < 300, status, text: async () => JSON.stringify(body), json: async () => body });
  server.fetch = async (url, options = {}) => {
    const path = String(url).replace(/^https?:\/\/[^/]+/, '');
    const method = options.method || 'GET';
    const body = options.body ? JSON.parse(options.body) : undefined;
    server.requests.push({ method, path, body });
    if (path === '/api/v1/auth/csrf') return json(200, { csrf_token: 'test-token' });
    if (path === '/api/v1/auth/me') return json(200, { user: server.user });
    if (path === '/api/v1/auth/prefs') {
      if (server.holdNext) { const hold = server.holdNext; server.holdNext = null; await hold; }
      if (server.failNext) { const fail = server.failNext; server.failNext = null; if (fail === 'network') throw new TypeError('offline'); return json(fail, { error: 'boom', code: fail === 401 ? 'auth_required' : 'internal_error' }); }
      if (!server.user) return json(401, { error: 'Login required', code: 'auth_required' });
      const id = server.user.id;
      const current = sanitize(server.prefs.get(id) || {});
      if (method === 'GET') return json(200, { prefs: current });
      if (method === 'PUT') {
        const remove = body.remove;
        let merged = merge(current, body.prefs);
        const gone = new Set(remove && Array.isArray(remove.saved) ? remove.saved : []);
        if (gone.size) { const kept = (merged.saved || []).filter((x) => !gone.has(x)); if (kept.length) merged.saved = kept; else delete merged.saved; }
        for (const key of Array.isArray(remove && remove.fields) ? remove.fields : []) if (['area', 'ptype', 'sort'].includes(key)) delete merged[key];   // G5.3c: clear a home filter
        const final = sanitize(merged);
        const evicted = (current.saved || []).filter((x) => !(final.saved || []).includes(x) && !gone.has(x));
        if (evicted.length) return json(409, { error: 'You can save up to 30 properties. Remove one first.', code: 'saved_limit' });
        server.prefs.set(id, final);
        return json(200, { prefs: final });
      }
    }
    return json(404, { error: 'not found', code: 'not_found' });
  };
  return server;
}
