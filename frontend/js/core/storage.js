/* Safe wrappers around localStorage / sessionStorage.
 * Browsers throw when storage is blocked (private mode, sandboxed iframes) or full;
 * every call here swallows that and returns the fallback instead of crashing the app. */
function makeArea(kind) {
  const area = () => {
    try { return globalThis[kind] || null; } catch (_) { return null; }
  };
  return {
    getRaw(key, fallback = null) {
      try { const v = area()?.getItem(key); return v == null ? fallback : v; } catch (_) { return fallback; }
    },
    setRaw(key, value) {
      try { area()?.setItem(key, String(value)); return true; } catch (_) { return false; }
    },
    getJSON(key, fallback = null) {
      try { const raw = area()?.getItem(key); return raw == null ? fallback : JSON.parse(raw); } catch (_) { return fallback; }
    },
    setJSON(key, value) {
      try { area()?.setItem(key, JSON.stringify(value)); return true; } catch (_) { return false; }
    },
    remove(key) {
      try { area()?.removeItem(key); } catch (_) { /* ignore */ }
    },
  };
}

export const local = makeArea('localStorage');
export const session = makeArea('sessionStorage');
