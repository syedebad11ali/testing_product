import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', '..');

/* A tiny cookie jar behind document.cookie (Max-Age=0 deletes). */
const sharedJar = new Map();
function installJar(protocol = 'https:') {
  const jar = sharedJar;
  Object.defineProperty(globalThis, 'document', { configurable: true, value: {
    get cookie() { return [...jar].map(([k, v]) => `${k}=${v}`).join('; '); },
    set cookie(line) {
      const [pair, ...attrs] = line.split('; ');
      const i = pair.indexOf('=');
      const [name, value] = [pair.slice(0, i), pair.slice(i + 1)];
      if (attrs.some(a => a === 'Max-Age=0')) jar.delete(name); else jar.set(name, value);
      installJar.lastLine = line;
    },
  } });
  Object.defineProperty(globalThis, 'location', { configurable: true, value: { protocol } });
  return jar;
}

const jar = installJar();
const C = await import('../../frontend/js/core/cookies.js');
const P = await import('../../frontend/js/core/prefs.js');
const reset = () => { jar.clear(); C._resetForTests(); };

test('prefs: same cases as the Python validator', () => {
  const cases = JSON.parse(fs.readFileSync(path.join(root, 'tests', 'shared', 'prefs_cases.json'), 'utf8'));
  assert.ok(cases.length >= 14);
  for (const { raw, expected } of cases) assert.deepEqual(P.sanitize(raw), expected, JSON.stringify(raw).slice(0, 80));
});

test('prefs: merge unions lists and lets cookie scalars win', () => {
  const m = P.merge({ theme: 'light', saved: ['A1', 'B2'] }, { theme: 'dark', saved: ['C3', 'A1'] });
  assert.equal(m.theme, 'dark');
  assert.deepEqual(m.saved, ['C3', 'A1', 'B2']);
});

test('policy version matches the backend', () => {
  const py = fs.readFileSync(path.join(root, 'backend', 'security', 'consent.py'), 'utf8');
  assert.equal(Number(/COOKIE_POLICY_VERSION = (\d+)/.exec(py)[1]), C.COOKIE_POLICY_VERSION);
});

test('nothing is stored before consent; the theme choice still works for this visit', () => {
  reset();
  assert.equal(C.readConsent(), null);
  const merged = C.writePrefs({ theme: 'dark' });
  assert.equal(merged.theme, 'dark');
  assert.equal(C.getCookie(C.PREFS_COOKIE), '', 'no kpt_prefs cookie without consent');
  assert.equal(C.readPrefs().theme, 'dark');
});

test('accepting Preferences persists prefs; rejecting removes them', () => {
  reset();
  C.writePrefs({ theme: 'dark' });
  assert.ok(C.writeConsent({ preferences: true, analytics: false }));
  assert.equal(JSON.parse(C.getCookie(C.PREFS_COOKIE)).theme, 'dark', 'choice made before consent is saved once allowed');
  assert.deepEqual(C.readConsent(), { preferences: true, analytics: false });
  C.writeConsent({ preferences: false, analytics: false });
  assert.equal(C.getCookie(C.PREFS_COOKIE), '');
});

test('cookie flags: SameSite=Lax, Path=/, Secure on https only, finite lifetime', () => {
  reset(); installJar('https:');
  C.writeConsent({ preferences: true });
  assert.match(installJar.lastLine, /Max-Age=\d+; Path=\/; SameSite=Lax; Secure$/);
  assert.ok(!/HttpOnly/.test(installJar.lastLine));
});

test('tampered, oversized or stale cookies are ignored safely', () => {
  reset();
  C.writeConsent({ preferences: true });
  jar.set('kpt_prefs', encodeURIComponent('{not json'));
  assert.deepEqual(C.readPrefs(), {});
  jar.set('kpt_prefs', encodeURIComponent(JSON.stringify({ theme: '<script>', role: 'admin', email: 'a@b.com', recent: ['<x>'] })));
  assert.deepEqual(C.readPrefs(), {});
  jar.set('kpt_consent', encodeURIComponent('v=99&p=1&a=1'));  // old/unknown policy version = ask again
  assert.equal(C.readConsent(), null);
  jar.set('kpt_consent', '%E0%A4%A');                          // broken escape must not throw
  assert.equal(C.readConsent(), null);
});

test('cookies never hold personal data: only known short codes survive', () => {
  reset();
  C.writeConsent({ preferences: true });
  C.writePrefs({ theme: 'dark', email: 'sara@example.com', name: 'Sara Khan', token: 'abc', recent: ['DEMO-KPT-8103', 'sara@example.com'] });
  const stored = C.getCookie(C.PREFS_COOKIE);
  assert.ok(!/sara|@|token|Khan/i.test(stored), stored);
  assert.ok(stored.length < 1000);
});

test('Forget me clears every cookie this script owns', () => {
  reset();
  C.writeConsent({ preferences: true }); C.writePrefs({ theme: 'dark' });
  C.clearBrowserState();
  assert.equal(C.getCookie(C.PREFS_COOKIE) + C.getCookie(C.CONSENT_COOKIE), '');
  assert.deepEqual(C.readPrefs(), {});
});

test('blocked cookies never throw', () => {
  Object.defineProperty(globalThis, 'document', { configurable: true, value: { get cookie() { throw new Error('blocked'); }, set cookie(_) { throw new Error('blocked'); } } });
  assert.equal(C.getCookie('x'), '');
  assert.equal(C.setCookie('x', '1'), false);
  assert.doesNotThrow(() => C.writePrefs({ theme: 'dark' }));
  installJar();
});

test('no template or script still stores UI preferences in localStorage', () => {
  const offenders = [];
  for (const f of ['js/features/theme.js', 'js/theme-init.js', 'index.html', 'login.html', 'admin.html']) {
    if (/kpt-theme|localStorage/.test(fs.readFileSync(path.join(root, 'frontend', f), 'utf8'))) offenders.push(f);
  }
  assert.deepEqual(offenders, []);
});

test('recently viewed: newest first, no duplicates, capped at 20, junk ids dropped', () => {
  reset();
  C.writeConsent({ preferences: true });
  C.addRecent('DEMO-KPT-1'); C.addRecent('DEMO-KPT-2'); C.addRecent('DEMO-KPT-1');
  assert.deepEqual(JSON.parse(C.getCookie(C.PREFS_COOKIE)).recent, ['DEMO-KPT-1', 'DEMO-KPT-2']);
  for (let i = 0; i < 30; i++) C.addRecent(`P${i}`);
  assert.equal(C.readPrefs().recent.length, 20);
  C.addRecent('<script>alert(1)</script>');
  assert.ok(!JSON.stringify(C.readPrefs()).includes('script'));
});

test('recently viewed is not persisted without Preferences consent', () => {
  reset();
  C.addRecent('DEMO-KPT-9');
  assert.equal(C.getCookie(C.PREFS_COOKIE), '');
  assert.deepEqual(C.readPrefs().recent, ['DEMO-KPT-9']);
});
