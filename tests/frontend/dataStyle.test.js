import test from 'node:test';
import assert from 'node:assert/strict';
import { applyDataStyle, clampPct, cssUrl, resolveUrl } from '../../frontend/js/ui/dataStyle.js';

const fake = (attrs) => {
  const set = {}; const props = {};
  return { nodeType: 1, getAttribute: (n) => (n in attrs ? attrs[n] : null), style: { set width(v) { set.width = v; }, setProperty: (k, v) => { props[k] = v; } }, set, props };
};

test('clampPct bounds and sanitises widths', () => {
  assert.deepEqual([clampPct(42), clampPct('7.5'), clampPct(-5), clampPct(250), clampPct('x'), clampPct(undefined), clampPct(NaN)], [42, 7.5, 0, 100, 0, 0, 0]);
});

test('cssUrl quotes and escapes so a value cannot break out of url()', () => {
  assert.equal(cssUrl('assets/Property Images/a b.jpg'), 'url("assets/Property Images/a b.jpg")');
  assert.equal(cssUrl('x");background:red;("'), 'url("x\\");background:red;(\\"")');
  assert.equal(cssUrl('a\\b\nc'), 'url("a\\\\b c")');
});

test('applyDataStyle writes the width and the image variable through the CSSOM only', () => {
  const el = fake({ 'data-w': '120', 'data-bg': 'https://kpt.example/assets/x.jpg' });
  applyDataStyle(el);
  assert.equal(el.set.width, '100%');
  assert.deepEqual(el.props, { '--img': 'url("https://kpt.example/assets/x.jpg")' });
  const none = fake({}); applyDataStyle(none); applyDataStyle(null); applyDataStyle({ nodeType: 3 });
  assert.deepEqual(none.set, {});
});

test('resolveUrl makes relative image paths absolute against the page, not the stylesheet', () => {
  assert.equal(resolveUrl('assets/Property Images/a.jpg', 'https://kpt.example/'), 'https://kpt.example/assets/Property%20Images/a.jpg');
  assert.equal(resolveUrl('/assets/a.jpg', 'https://kpt.example/some/page'), 'https://kpt.example/assets/a.jpg');
  assert.equal(resolveUrl('https://cdn.example/a.jpg', 'https://kpt.example/'), 'https://cdn.example/a.jpg');
});
