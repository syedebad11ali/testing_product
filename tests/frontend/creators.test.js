import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';
import { shouldClose } from '../../frontend/js/features/creators.js';

const FE = fileURLToPath(new URL('../../frontend/', import.meta.url));
const html = readFileSync(join(FE, 'index.html'), 'utf8');
const menu = /<details class="creators-menu"[\s\S]*?<\/details>/.exec(html)?.[0] || '';

test('the Creators menu is in the header with both credits, safe links and no remote images', () => {
  assert.ok(menu, 'creators menu present in index.html');
  assert.match(menu, /<summary aria-label="Creators">/);
  const links = [...menu.matchAll(/<a href="([^"]+)" target="_blank" rel="noopener noreferrer">/g)].map((m) => m[1]);
  assert.deepEqual(links, ['https://github.com/syedebad11ali', 'https://github.com/ctrl-shift-ali']);
  assert.match(menu, /Syed Ebad Ali/);
  assert.match(menu, /M Ali Abeer/);
  assert.doesNotMatch(menu, /<img|\sstyle=|\sonclick=|<script/i);  // strict CSP: img-src 'self' data: blob:, no inline styles/handlers
  assert.ok(html.indexOf('id="creatorsMenu"') < html.indexOf('id="authLink"'), 'sits before the auth buttons');
  assert.match(html, /<link rel="stylesheet" href="css\/creators\.css">/);
});

test('shouldClose: Escape, outside click and link click close an open menu; inside clicks and closed menus do not', () => {
  const inside = {};
  const link = { closest: (sel) => (sel === '.creators-dropdown a' ? {} : null) };
  const open = { open: true, contains: (t) => t === inside || t === link };
  const closed = { open: false, contains: () => true };
  assert.equal(shouldClose({ type: 'keydown', key: 'Escape' }, open), true);
  assert.equal(shouldClose({ type: 'keydown', key: 'a' }, open), false);
  assert.equal(shouldClose({ type: 'click', target: {} }, open), true);            // outside
  assert.equal(shouldClose({ type: 'click', target: inside }, open), false);        // inside, not a link
  assert.equal(shouldClose({ type: 'click', target: link }, open), true);           // a credit link
  assert.equal(shouldClose({ type: 'keydown', key: 'Escape' }, closed), false);
  assert.equal(shouldClose({ type: 'click', target: {} }, null), false);
});
