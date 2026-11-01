/* Shared "Login required" dialog and the safe return path used by it.
 * Display only: the server is the authority (guests get 403 guest_not_allowed on account features). No inline script or style. */

export const TITLE = 'Login required';
export const MESSAGE = 'Create an account or log in to use this feature.';
export const BUTTON = 'Log in / Sign up';
const MAX_NEXT = 2048;
const MAX_FEATURE = 80;

/** A same-origin path to return to after logging in; `/` for anything else. Keeps hash routes such as `/#/property/p1`.
 *  Rejects `//host`, `scheme:`, backslashes, control characters, and a missing/overlong value. No URL parsing is needed: the strict format above can only be an internal path. */
export function safeNext(value) {
  if (typeof value !== 'string' || !value || value.length > MAX_NEXT) return '/';
  if (!/^\/(?![/\\])/.test(value)) return '/';            // a single leading slash only: no `//host`, `/\host`, `https:`, `javascript:`
  if (/[\u0000-\u001f\u007f-\u009f\\]/.test(value)) return '/';   // control characters and backslashes anywhere
  return value;
}

/** `/login?next=<encoded safe path>` */
export function loginUrl(next) {
  return `/login?next=${encodeURIComponent(safeNext(next))}`;
}

function currentPath() {
  const loc = globalThis.location;
  return loc && typeof loc.pathname === 'string' ? `${loc.pathname}${loc.search || ''}${loc.hash || ''}` : '/';
}

/** True unless the element is known to be invisible: no size, or entirely outside the viewport (e.g. an item inside the closed off-canvas
 *  drawer). Focus is only handed back to something the visitor can see; an element without layout information counts as visible. */
function isOnScreen(node) {
  if (!node || typeof node.getBoundingClientRect !== 'function') return true;
  const r = node.getBoundingClientRect();
  const vw = globalThis.innerWidth || 0, vh = globalThis.innerHeight || 0;
  if (!(r.width > 0 && r.height > 0)) return false;
  return !(r.right <= 0 || r.bottom <= 0 || (vw > 0 && r.left >= vw) || (vh > 0 && r.top >= vh));
}

/** Where focus goes when the dialog closes. The opener, if the visitor can still use it; an opener inside the side drawer only while the
 *  drawer is open (`closeDrawer()` removes `.open` at once, though the slide-out takes 250 ms, so geometry cannot be trusted mid-transition);
 *  otherwise the visible menu button; otherwise nothing. */
function usable(node) {
  if (!node || typeof node.focus !== 'function' || node.isConnected === false || node.disabled) return false;
  if (typeof node.closest === 'function' && (node.closest('[hidden],[inert],[aria-hidden="true"]'))) return false;
  return isOnScreen(node);
}
function focusTarget(opener) {
  const inClosedDrawer = typeof opener?.closest === 'function' && (() => { const d = opener.closest('.drawer'); return Boolean(d) && !d.classList.contains('open'); })();
  if (!inClosedDrawer && usable(opener)) return opener;
  const toggle = typeof document.querySelector === 'function' ? document.querySelector('.topnav-menu') : null;
  return usable(toggle) ? toggle : null;
}

let active = null;   // the one open dialog: { element, close }

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

/** Opens the dialog (or returns the one already open). `feature` is optional context shown as a small line under the message;
 *  `next` is where to return after login (defaults to the current page; always passed through safeNext). */
export function showLoginRequired({ feature, next } = {}) {
  if (active && active.element.isConnected !== false) return active;

  const opener = document.activeElement || null;
  const backdrop = el('div', 'login-prompt-bg');
  const box = el('div', 'login-prompt');
  box.setAttribute('role', 'dialog');
  box.setAttribute('aria-modal', 'true');
  box.setAttribute('aria-labelledby', 'loginPromptTitle');
  box.setAttribute('aria-describedby', 'loginPromptText');

  const title = el('h2', 'login-prompt-title', TITLE); title.id = 'loginPromptTitle';
  const text = el('p', 'login-prompt-text', MESSAGE); text.id = 'loginPromptText';
  box.appendChild(title);
  box.appendChild(text);
  const name = typeof feature === 'string' ? feature.replace(/[\u0000-\u001f\u007f-\u009f]/g, ' ').trim().slice(0, MAX_FEATURE) : '';
  if (name) box.appendChild(el('p', 'login-prompt-feature', `Feature: ${name}`));

  const actions = el('div', 'login-prompt-actions');
  const go = el('a', 'login-prompt-btn login-prompt-primary', BUTTON);
  go.href = loginUrl(next === undefined ? currentPath() : next);
  const later = el('button', 'login-prompt-btn login-prompt-secondary', 'Not now');
  later.type = 'button';
  actions.appendChild(go);
  actions.appendChild(later);
  box.appendChild(actions);
  backdrop.appendChild(box);

  function close() {
    document.removeEventListener('keydown', onKey);
    backdrop.remove();
    active = null;
    const back = focusTarget(opener);
    if (back) back.focus();
  }
  function onKey(e) {
    if (e.key === 'Escape') { e.preventDefault(); close(); return; }
    if (e.key !== 'Tab') return;
    const items = [go, later];                               // keep keyboard focus inside the dialog
    const i = items.indexOf(document.activeElement);
    const to = e.shiftKey ? (i <= 0 ? items.length - 1 : i - 1) : (i === -1 || i === items.length - 1 ? 0 : i + 1);
    e.preventDefault();
    items[to].focus();
  }
  later.addEventListener('click', close);
  backdrop.addEventListener('click', (e) => { if (e.target === backdrop) close(); });
  document.addEventListener('keydown', onKey);

  document.body.appendChild(backdrop);
  go.focus();
  active = { element: box, close };
  return active;
}
