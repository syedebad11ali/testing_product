import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

/* A tiny fake DOM, just enough for the dialog (tree, attributes, events, focus). No test dependency is added. */
class FakeEl {
  constructor(tag) {
    this.tagName = tag.toUpperCase(); this.children = []; this.parentNode = null; this.attrs = {}; this.listeners = {};
    this.className = ''; this.textContent = ''; this.id = ''; this.href = ''; this.type = '';
  }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return this.attrs[k] ?? null; }
  appendChild(c) { c.parentNode = this; this.children.push(c); return c; }
  addEventListener(t, f) { (this.listeners[t] ||= []).push(f); }
  removeEventListener(t, f) { this.listeners[t] = (this.listeners[t] || []).filter((x) => x !== f); }
  dispatch(t, e = {}) { const ev = { target: this, defaultPrevented: false, preventDefault() { this.defaultPrevented = true; }, ...e }; (this.listeners[t] || []).slice().forEach((f) => f(ev)); return ev; }
  click() { return this.dispatch('click'); }
  focus() { globalThis.document.activeElement = this; }
  remove() { if (this.parentNode) { this.parentNode.children = this.parentNode.children.filter((c) => c !== this); this.parentNode = null; } }
  get isConnected() { let n = this; while (n.parentNode) n = n.parentNode; return n === globalThis.document.body; }
  find(pred, out = []) { this.children.forEach((c) => { if (pred(c)) out.push(c); c.find(pred, out); }); return out; }
}

function installDom() {
  const body = new FakeEl('body');
  const docListeners = {};
  globalThis.document = {
    body, activeElement: null,
    createElement: (tag) => new FakeEl(tag),
    addEventListener: (t, f) => { (docListeners[t] ||= []).push(f); },
    removeEventListener: (t, f) => { docListeners[t] = (docListeners[t] || []).filter((x) => x !== f); },
    key(key, extra = {}) { const ev = { key, shiftKey: false, defaultPrevented: false, preventDefault() { this.defaultPrevented = true; }, ...extra }; (docListeners.keydown || []).slice().forEach((f) => f(ev)); return ev; },
    listenerCount: (t) => (docListeners[t] || []).length,
  };
  globalThis.location = { pathname: '/', search: '', hash: '' };
  return body;
}

const mod = await import('../../frontend/js/features/loginPrompt.js');
const { safeNext, loginUrl, showLoginRequired, TITLE, MESSAGE, BUTTON } = mod;

const dialogs = (body) => body.find((n) => n.attrs.role === 'dialog');
const byClass = (root, cls) => root.find((n) => n.className.split(' ').includes(cls))[0];

test('safeNext keeps valid same-origin paths', () => {
  for (const ok of ['/', '/listings', '/listings?area=Gulshan&limit=5', '/messages?c=1', '/admin', '/a/b/c', '/path#frag']) assert.equal(safeNext(ok), ok, ok);
});

test('safeNext keeps legitimate hash routes', () => {
  for (const ok of ['/#/property/p1', '/#/home', '/#/verify-document', '/listings#/x']) assert.equal(safeNext(ok), ok, ok);
});

test('safeNext rejects every unsafe or external target', () => {
  const bad = ['//evil.com', '//evil.com/path', 'https://evil.com', 'http://evil.com/x', 'javascript:alert(1)', 'JaVaScRiPt:alert(1)', 'data:text/html,x',
    '/\\evil', '/\\\\evil.com', '/a\\b', '\\evil', 'evil.com', 'listings', '', ' /listings', '/list\u0000ings', '/list\ningss', '/a\tb', '/a\rb', '/\u007f', '/\u0085x',
    '/' + 'a'.repeat(2048), '/\\/evil.com', '///evil.com', '/%5Cevil/../..\\x'];
  for (const value of bad) assert.equal(safeNext(value), '/', JSON.stringify(value).slice(0, 60));
});

test('safeNext returns "/" for missing or non-string values', () => {
  for (const v of [undefined, null, 0, 5, true, {}, [], ['/x'], () => '/x']) assert.equal(safeNext(v), '/');
  assert.equal(safeNext('/' + 'a'.repeat(2000)), '/' + 'a'.repeat(2000));   // long but within the limit is fine
});

test('loginUrl encodes the safe path and never an unsafe one', () => {
  assert.equal(loginUrl('/#/property/p1'), '/login?next=%2F%23%2Fproperty%2Fp1');
  assert.equal(loginUrl('/listings?area=a&b=c'), '/login?next=%2Flistings%3Farea%3Da%26b%3Dc');
  assert.equal(loginUrl('//evil.com'), '/login?next=%2F');
  assert.equal(loginUrl('javascript:alert(1)'), '/login?next=%2F');
  assert.equal(loginUrl(undefined), '/login?next=%2F');
  assert.equal(decodeURIComponent(loginUrl('/#/property/p1').split('next=')[1]), '/#/property/p1');
});

test('dialog shows the required title, message and button with dialog semantics', () => {
  const body = installDom();
  showLoginRequired({ feature: 'Chat with our assistant', next: '/#/property/p1' });
  const [box] = dialogs(body);
  assert.ok(box, 'a dialog is in the page');
  assert.equal(box.attrs['aria-modal'], 'true');
  assert.equal(TITLE, 'Login required'); assert.equal(MESSAGE, 'Create an account or log in to use this feature.'); assert.equal(BUTTON, 'Log in / Sign up');
  const title = byClass(box, 'login-prompt-title'), text = byClass(box, 'login-prompt-text'), go = byClass(box, 'login-prompt-primary');
  assert.equal(title.textContent, 'Login required');
  assert.equal(text.textContent, 'Create an account or log in to use this feature.');
  assert.equal(go.textContent, 'Log in / Sign up');
  assert.equal(box.attrs['aria-labelledby'], title.id); assert.equal(box.attrs['aria-describedby'], text.id);
  assert.equal(byClass(box, 'login-prompt-feature').textContent, 'Feature: Chat with our assistant');
  assert.equal(go.href, '/login?next=%2F%23%2Fproperty%2Fp1');
});

test('the login destination is always an encoded safe path; default is the current page', () => {
  let body = installDom();
  showLoginRequired({ next: '//evil.com' });
  assert.equal(byClass(dialogs(body)[0], 'login-prompt-primary').href, '/login?next=%2F');
  body = installDom();
  globalThis.location = { pathname: '/listings', search: '?area=Gulshan', hash: '#/x' };
  showLoginRequired({});
  assert.equal(byClass(dialogs(body)[0], 'login-prompt-primary').href, '/login?next=%2Flistings%3Farea%3DGulshan%23%2Fx');
  body = installDom();
  showLoginRequired();   // no argument at all
  assert.equal(dialogs(body).length, 1);
});

test('feature text is context only: the message is unchanged, markup and control characters are not interpreted', () => {
  const body = installDom();
  showLoginRequired({ feature: '<img src=x onerror=alert(1)>\u0000\n' + 'x'.repeat(200) });
  const [box] = dialogs(body);
  assert.equal(byClass(box, 'login-prompt-text').textContent, 'Create an account or log in to use this feature.');
  const f = byClass(box, 'login-prompt-feature').textContent;
  assert.ok(f.startsWith('Feature: <img'), 'shown as plain text');
  assert.ok(f.length <= 'Feature: '.length + 80);
  assert.ok(!/[\u0000-\u001f]/.test(f));
  assert.equal(box.find((n) => n.tagName === 'IMG').length, 0, 'no element was created from the text');
  const none = installDom(); showLoginRequired({ feature: 5 }); assert.equal(byClass(dialogs(none)[0], 'login-prompt-feature'), undefined);
});

test('G3 review: focus is not returned to an opener that is off screen (a closed drawer item); an on-screen opener still gets it', () => {
  globalThis.innerWidth = 390; globalThis.innerHeight = 844;
  const rectOf = (left, top, right, bottom) => () => ({ left, top, right, bottom, width: right - left, height: bottom - top });
  const body = installDom();
  const hidden = new FakeEl('button'); hidden.getBoundingClientRect = rectOf(-303, 377, -27, 439); body.appendChild(hidden); hidden.focus();
  showLoginRequired({ feature: 'Owner verification' }); globalThis.document.key('Escape');
  assert.equal(dialogs(body).length, 0);
  assert.notEqual(globalThis.document.activeElement, hidden, 'focus must not move to an element inside the off-canvas drawer');
  const zero = new FakeEl('button'); zero.getBoundingClientRect = rectOf(0, 0, 0, 0); body.appendChild(zero); zero.focus();
  showLoginRequired({}); globalThis.document.key('Escape');
  assert.notEqual(globalThis.document.activeElement, zero, 'a zero-size (display:none) opener is not focused either');
  const visible = new FakeEl('button'); visible.getBoundingClientRect = rectOf(20, 100, 120, 146); body.appendChild(visible); visible.focus();
  showLoginRequired({}); globalThis.document.key('Escape');
  assert.equal(globalThis.document.activeElement, visible);
  delete globalThis.innerWidth; delete globalThis.innerHeight;
});

/* G3 review (A8b): drawer fixtures. `closeDrawer()` removes `.open` at once while the 250 ms slide-out is still running, so the opener's
 * rectangle is still on screen when the dialog closes: the drawer state, not geometry, decides. */
function drawerFixture({ open }) {
  globalThis.innerWidth = 390; globalThis.innerHeight = 844;
  const rect = (l, t, r, b) => () => ({ left: l, top: t, right: r, bottom: b, width: r - l, height: b - t });
  const body = installDom();
  const drawer = new FakeEl('div'); drawer.classList = { contains: (c) => c === 'open' && open }; body.appendChild(drawer);
  const item = new FakeEl('button'); drawer.appendChild(item);
  item.getBoundingClientRect = rect(12, 394, 288, 456);                  // still ON screen: the slide has not moved it yet
  item.closest = (sel) => (sel === '.drawer' ? drawer : null);
  const toggle = new FakeEl('button'); toggle.className = 'topnav-menu'; body.appendChild(toggle); toggle.getBoundingClientRect = rect(330, 20, 374, 64);
  globalThis.document.querySelector = (sel) => (sel === '.topnav-menu' ? toggle : null);
  item.focus();
  return { body, item, toggle };
}
const endDrawerFixture = () => { delete globalThis.innerWidth; delete globalThis.innerHeight; };

test('G3 review A8b: opened from the closing drawer, Escape moves focus to the menu button, not the sliding drawer item', () => {
  const { body, item, toggle } = drawerFixture({ open: false });
  showLoginRequired({ feature: 'Owner verification' });
  globalThis.document.key('Escape');
  assert.equal(dialogs(body).length, 0);
  assert.equal(globalThis.document.activeElement, toggle);
  assert.notEqual(globalThis.document.activeElement, item);
  assert.equal(globalThis.document.listenerCount('keydown'), 0);
  endDrawerFixture();
});

test('G3 review A8b: "Not now" from the closing drawer also lands on the menu button', () => {
  const { body, toggle } = drawerFixture({ open: false });
  const { element } = showLoginRequired({});
  byClass(element, 'login-prompt-secondary').click();
  assert.equal(dialogs(body).length, 0);
  assert.equal(globalThis.document.activeElement, toggle);
  assert.equal(globalThis.document.listenerCount('keydown'), 0);
  endDrawerFixture();
});

test('G3 review A8b: an opener inside a drawer that is still open keeps normal restoration', () => {
  const { item } = drawerFixture({ open: true });
  showLoginRequired({}); globalThis.document.key('Escape');
  assert.equal(globalThis.document.activeElement, item);
  endDrawerFixture();
});

test('G3 review A8b: no usable opener and no visible menu button: nothing is focused (no crash)', () => {
  const { body, item, toggle } = drawerFixture({ open: false });
  toggle.getBoundingClientRect = () => ({ left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0 });
  showLoginRequired({}); globalThis.document.key('Escape');
  assert.equal(dialogs(body).length, 0);
  assert.notEqual(globalThis.document.activeElement, item);
  assert.notEqual(globalThis.document.activeElement, toggle);
  endDrawerFixture();
});

test('G3 review A8b: a disabled or hidden opener falls back to the menu button', () => {
  const { item, toggle } = drawerFixture({ open: true });
  item.disabled = true;
  showLoginRequired({}); globalThis.document.key('Escape');
  assert.equal(globalThis.document.activeElement, toggle);
  item.disabled = false; item.focus();
  const orig = item.closest; item.closest = (sel) => (sel === '.drawer' ? orig(sel) : (sel.includes('[hidden]') ? item : null));
  showLoginRequired({}); globalThis.document.key('Escape');
  assert.equal(globalThis.document.activeElement, toggle);
  endDrawerFixture();
});

test('G3 review A8b: repeated open/close from the drawer never duplicates the dialog or leaks key listeners', () => {
  const { body, toggle } = drawerFixture({ open: false });
  for (let i = 0; i < 4; i += 1) {
    const first = showLoginRequired({}); const second = showLoginRequired({});
    assert.equal(first, second); assert.equal(dialogs(body).length, 1); assert.equal(globalThis.document.listenerCount('keydown'), 1);
    if (i % 2) byClass(first.element, 'login-prompt-secondary').click(); else globalThis.document.key('Escape');
    assert.equal(dialogs(body).length, 0); assert.equal(globalThis.document.listenerCount('keydown'), 0);
    assert.equal(globalThis.document.activeElement, toggle); toggle.focus();
  }
  endDrawerFixture();
});

test('focus moves into the dialog; Escape closes it and focus returns to the opener', () => {
  const body = installDom();
  const opener = new FakeEl('button'); body.appendChild(opener); opener.focus();
  const { element } = showLoginRequired({ feature: 'Save' });
  assert.equal(globalThis.document.activeElement, byClass(element, 'login-prompt-primary'));
  const ev = globalThis.document.key('Escape');
  assert.ok(ev.defaultPrevented);
  assert.equal(dialogs(body).length, 0);
  assert.equal(globalThis.document.activeElement, opener);
  assert.equal(globalThis.document.listenerCount('keydown'), 0, 'the key listener is removed on close');
});

test('"Not now" and a click on the backdrop close; a click inside the dialog does not', () => {
  let body = installDom();
  let r = showLoginRequired();
  byClass(r.element, 'login-prompt-secondary').click();
  assert.equal(dialogs(body).length, 0);
  body = installDom(); r = showLoginRequired();
  const backdrop = r.element.parentNode;
  backdrop.dispatch('click', { target: r.element });
  assert.equal(dialogs(body).length, 1, 'click inside the box keeps it open');
  backdrop.dispatch('click', { target: backdrop });
  assert.equal(dialogs(body).length, 0);
});

test('Tab and Shift+Tab stay inside the dialog', () => {
  installDom();
  const { element } = showLoginRequired();
  const go = byClass(element, 'login-prompt-primary'), later = byClass(element, 'login-prompt-secondary');
  assert.equal(globalThis.document.activeElement, go);
  globalThis.document.key('Tab'); assert.equal(globalThis.document.activeElement, later);
  globalThis.document.key('Tab'); assert.equal(globalThis.document.activeElement, go);
  globalThis.document.key('Tab', { shiftKey: true }); assert.equal(globalThis.document.activeElement, later);
  globalThis.document.key('Tab', { shiftKey: true }); assert.equal(globalThis.document.activeElement, go);
});

test('a second call while open does not create a second dialog; it can be opened again after closing', () => {
  const body = installDom();
  const a = showLoginRequired({ feature: 'One' });
  const b = showLoginRequired({ feature: 'Two' });
  assert.equal(a, b);
  assert.equal(dialogs(body).length, 1);
  assert.equal(globalThis.document.listenerCount('keydown'), 1);
  a.close();
  assert.equal(dialogs(body).length, 0);
  showLoginRequired({ feature: 'Three' });
  assert.equal(dialogs(body).length, 1);
  assert.equal(byClass(dialogs(body)[0], 'login-prompt-feature').textContent, 'Feature: Three');
});

test('source and styles: no inline script/style, no dynamic markup; the stylesheet defines the dialog and is loaded by index.html', () => {
  const root = new URL('../../frontend/', import.meta.url);
  const js = readFileSync(fileURLToPath(new URL('js/features/loginPrompt.js', root)), 'utf8');
  assert.ok(!/innerHTML|insertAdjacentHTML|eval\(|new Function|onclick|\.cssText|setAttribute\(\s*['"]style/.test(js));
  assert.ok(!/\sstyle\s*=/.test(js));
  const css = readFileSync(fileURLToPath(new URL('css/overlays.css', root)), 'utf8');
  for (const sel of ['.login-prompt-bg', '.login-prompt{', '.login-prompt-primary', '.login-prompt-btn:focus-visible', '@keyframes loginPromptRise', 'prefers-reduced-motion', 'max-width:360px']) assert.ok(css.includes(sel), sel);
  const html = readFileSync(fileURLToPath(new URL('index.html', root)), 'utf8');
  assert.ok(/href="css\/overlays\.css"/.test(html), 'index.html loads overlays.css');
});
