import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { installDom } from './helpers/domStub.js';
import { createAccountServer } from './helpers/fakeAccountServer.js';

const { document } = installDom();
localStorage.setItem('kpt_favorite_properties', JSON.stringify(['p2', 17]));   // legacy global key: must be ignored (G5.2)
// G5.1/G5.2: favorites need an account and live on the account, so these tests run as a registered user against a fake account API
// (the gate is tested in favoritesAuthGate.test.js, the server-side behavior in favoritesServer.test.js)
const server = createAccountServer();
server.user = { id: 'u1', name: 'Sara', role: 'user' };
server.prefs.set('u1', { saved: ['p2'] });
globalThis.fetch = (...args) => server.fetch(...args);
const { state } = await import('../../frontend/js/state/store.js');
const { toggleSave, renderHome } = await import('../../frontend/js/features/home.js');
const { ensureFavoritesLoaded } = await import('../../frontend/js/features/favorites.js');
const { renderDetail, renderSubList } = await import('../../frontend/js/features/property.js');
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', '..');

function favoriteButton(id, type) {
  const attributes = { 'data-favorite-id': id };
  const classes = new Set();
  const content = { textContent: type === 'heart' ? '♡' : 'Save Property' };
  return {
    dataset: { favoriteId: id },
    classList: { toggle(name, active) { active ? classes.add(name) : classes.delete(name); }, contains(name) { return classes.has(name); } },
    setAttribute(name, value) { attributes[name] = value; },
    hasAttribute(name) { return name === 'data-favorite-label' && type === 'label'; },
    querySelector(selector) { return selector === '[data-favorite-label]' && type === 'label' || selector === '[data-favorite-heart]' && type === 'heart' ? content : null; },
    attributes,
    content,
    isSaved() { return classes.has('saved'); },
  };
}

test('favorites load from the account (not from storage) and update all visible controls without requiring the home grid', async () => {
  assert.deepEqual([...state.saved], [], 'the legacy global key is not loaded');
  assert.equal(await ensureFavoritesLoaded(), true);
  assert.deepEqual([...state.saved], ['p2']);
  assert.equal(localStorage.getItem('kpt_favorite_properties'), null);
  const heart = favoriteButton('p1', 'heart');
  const saveLabel = favoriteButton('p1', 'label');
  const unrelated = favoriteButton('p2', 'heart');
  document.querySelectorAll = () => [heart, saveLabel, unrelated];

  await toggleSave('p1');

  assert.equal(heart.isSaved(), true);
  assert.equal(heart.attributes['aria-pressed'], 'true');
  assert.equal(heart.attributes['aria-label'], 'Remove from saved properties');
  assert.equal(heart.content.textContent, '♥');
  assert.equal(saveLabel.content.textContent, 'Saved');
  assert.equal(unrelated.isSaved(), false);
  assert.deepEqual([...server.prefs.get('u1').saved].sort(), ['p1', 'p2']);
  assert.match(renderSubList('saved'), /5 Bed House/);
  assert.match(renderSubList('saved'), /3 Bed House/);

  await toggleSave('p1');
  assert.equal(heart.isSaved(), false);
  assert.equal(saveLabel.content.textContent, 'Save Property');
  assert.deepEqual(server.prefs.get('u1').saved, ['p2']);
  assert.doesNotMatch(renderSubList('saved'), /5 Bed House/);
});

test('home and detail favorite buttons expose pressed state and updateable labels', () => {
  const home = renderHome();
  const detail = renderDetail('p2');
  assert.match(home, /data-favorite-id="p2"/);
  assert.match(detail, /data-favorite-heart/);
  assert.match(detail, /data-favorite-label/);
  assert.match(detail, /aria-pressed="true"/);
});

test('favorite gradients use blue in light theme, green in dark theme, and pink-red hearts', () => {
  const base = fs.readFileSync(path.join(root, 'frontend', 'css', 'base.css'), 'utf8');
  const browse = fs.readFileSync(path.join(root, 'frontend', 'css', 'browse.css'), 'utf8');
  const property = fs.readFileSync(path.join(root, 'frontend', 'css', 'property.css'), 'utf8');
  assert.match(base, /--favorite-start:var\(--teal-700\)/);
  assert.match(base, /--favorite-end:var\(--teal-700\)/);
  assert.match(base, /--favorite-start:#087F5B/);
  assert.match(base, /--favorite-end:#35C98A/);
  assert.match(base, /--favorite-heart-start:#FF6685/);
  assert.match(base, /--favorite-heart-end:#D91F53/);
  assert.match(base, /:root\[data-theme="dark"\] \.favorite-heart\{-webkit-text-stroke:0\.5px #011425;?\}/);
  assert.match(base, /:root\[data-theme="dark"\] \.saved \.favorite-heart\{-webkit-text-stroke:0;?\}/);
  assert.match(browse, /\.fav\.saved\{background:linear-gradient\(135deg,var\(--favorite-start\),var\(--favorite-end\)\)/);
  assert.match(property, /\.favbtn\.saved\{background:linear-gradient\(135deg,var\(--favorite-start\),var\(--favorite-end\)\)/);
});
