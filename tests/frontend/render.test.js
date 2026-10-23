import test from 'node:test';
import assert from 'node:assert/strict';
import { installDom } from './helpers/domStub.js';

const { document } = installDom();
const { render, nav } = await import('../../frontend/js/app/router.js');
const { state, docState, resetDocState, ownerState } = await import('../../frontend/js/state/store.js');

const app = () => document.getElementById('app').innerHTML;

test('every view renders non-empty HTML without "undefined" leaking into it', () => {
  const views = [['home'], ['detail', 'p1'], ['verify', 'p2'], ['report', 'p5'], ['verlist'], ['savedlist'], ['reportslist'], ['ownerverify'], ['verify-document']];
  for (const [view, id] of views) {
    state.view = view; state.propId = id || null;
    render();
    assert.ok(app().length > 200, `${view} rendered too little`);
    assert.ok(!/>undefined<|="undefined"|\[object Object\]/.test(app()), `${view} leaked undefined`);
  }
});

test('unknown view falls back to home instead of a blank page', () => {
  state.view = 'does-not-exist'; render();
  assert.equal(state.view, 'home');
  assert.ok(app().length > 200);
});

test('a screen that throws shows the recovery card, not a blank page', () => {
  state.view = 'detail'; state.propId = 'p1';
  const originalError = console.error; console.error = () => {};
  try {
    state.view = 'report'; state.propId = { toString() { throw new Error('boom'); } }; // makes the renderer throw
    render();
  } finally { console.error = originalError; }
  assert.match(app(), /could not be displayed|Back to home/);
});

test('nav() resets the selected property when none is given', () => {
  nav('detail', 'p3'); assert.equal(state.propId, 'p3');
  nav('home'); assert.equal(state.propId, null);
});

test('resetDocState clears the wizard in place (same object identity)', () => {
  const ref = docState; docState.step = 'result'; docState.fields.x = 1;
  resetDocState();
  assert.equal(ref, docState);
  assert.equal(docState.step, 'landing');
  assert.deepEqual(docState.fields, {});
});

test('owner screen shows the loading state before the CSV store is ready', () => {
  ownerState.store = null; ownerState.error = null;
  state.view = 'ownerverify'; render();
  assert.match(app(), /owner-verification/);
});
