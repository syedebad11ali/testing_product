import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { googleButtonWidth } from '../../frontend/js/auth-page.js';

/* Google's button is an iframe of an exact pixel width (200-400). The login page asks for the width its container really has. */
test('googleButtonWidth follows the container inside Google\'s 200-400 px limits', () => {
  assert.equal(googleButtonWidth(288), 288);          // a 320 px phone
  assert.equal(googleButtonWidth(328), 328);          // a 360 px phone
  assert.equal(googleButtonWidth(420), 400);          // desktop column: capped
  assert.equal(googleButtonWidth(400), 400);
  assert.equal(googleButtonWidth(250.9), 250);
  assert.equal(googleButtonWidth(150), 200);          // narrower than Google allows: its minimum
});

test('googleButtonWidth is 0 while the container is not laid out (hidden form), so nothing is drawn at a wrong size', () => {
  for (const v of [0, -5, NaN, undefined, null, 'x', Infinity]) assert.equal(googleButtonWidth(v), 0, String(v));
});

test('the page no longer asks Google for a fixed 400 px and redraws when the container changes', () => {
  const src = readFileSync(new URL('../../frontend/js/auth-page.js', import.meta.url), 'utf8');
  assert.doesNotMatch(src, /renderButton\([^)]*width:\s*400/);
  assert.match(src, /new ResizeObserver\(draw\)/);
});

test('login CSS restores the Google G mask blocked by the page CSP and layers lead text above artwork', () => {
  const css = readFileSync(new URL('../../frontend/css/login.css', import.meta.url), 'utf8');
  assert.match(css, /\.gbox svg>g\{clip-path:path\(/);
  assert.match(css, /\.lead\{position:relative;z-index:4/);
  assert.match(css, /\.art\{position:relative;z-index:1/);
});
