import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';
import { shouldClose } from '../../frontend/js/features/creators.js';

const FE = fileURLToPath(new URL('../../frontend/', import.meta.url));
const html = readFileSync(join(FE, 'index.html'), 'utf8');
const menu = /<details class="creators-menu"[\s\S]*?<\/details>/.exec(html)?.[0] || '';

test('the Creators menu is in the header with both credits, profile avatars and safe links', () => {
  assert.ok(menu, 'creators menu present in index.html');
  assert.match(menu, /<summary aria-label="Creators">/);
  const links = [...menu.matchAll(/<a href="([^"]+)" target="_blank" rel="noopener noreferrer">/g)].map((m) => m[1]);
  assert.deepEqual(links, ['https://github.com/syedebad11ali', 'https://github.com/ctrl-shift-ali']);
  assert.match(menu, /Syed Ebad Ali/);
  assert.match(menu, /M Ali Abeer/);
  assert.match(menu, /<img class="creators-avatar" src="assets\/creators\/syedebad11ali\.jpg" alt="">/);
  assert.match(menu, /<img class="creators-avatar" src="assets\/creators\/ctrl-shift-ali\.jpg" alt="">/);
  assert.doesNotMatch(menu, /\sstyle=|\sonclick=|<script/i);  // no inline styles/handlers
  assert.ok(html.indexOf('id="creatorsMenu"') < html.indexOf('id="authLink"'), 'sits before the auth buttons');
  assert.match(html, /<link rel="stylesheet" href="css\/creators\.css">/);
});

test('mobile account menu uses text-only auth actions while desktop auth controls remain separate', () => {
  const account = /<details class="account-menu" id="accountMenu">([\s\S]*?)<\/details>/.exec(html)?.[0] || '';
  const authNav = readFileSync(join(FE, 'js', 'features', 'authNav.js'), 'utf8');
  const css = readFileSync(join(FE, 'css', 'creators.css'), 'utf8');
  const layout = readFileSync(join(FE, 'css', 'layout.css'), 'utf8');
  assert.ok(account.includes('aria-label="Account"'));
  assert.match(account, /<span class="account-label" id="mobileAccountName">Account<\/span>/);
  assert.ok(account.includes('id="mobileAuthLink"'));
  assert.match(account, /href="\/login"/);
  assert.match(account, /href="\/signup"/);
  assert.doesNotMatch(account, /<img\b/);
  assert.match(authNav, /for \(const target of \[slot, mobileSlot\]\)/);
  assert.match(authNav, /accountLabel\.textContent = user \? \(user\.role === 'guest' \? 'Guest' : user\.name\.split\(' '\)\[0\]\) : 'Account'/);
  assert.match(css, /@media \(max-width:640px\)\{\.account-menu\{display:block\}/);
  assert.match(css, /\.account-dropdown\{position:absolute;top:calc\(100% \+ 8px\);right:18px;left:-15px;width:220px/);
  assert.match(css, /\.account-dropdown \.auth-slot>\*\{[^}]*width:100%/);
  assert.match(layout, /@media \(max-width:640px\)[\s\S]*?\.topnav-inner>\.auth-slot\{display:none\}/);
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
