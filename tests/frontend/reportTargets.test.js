import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { reportChoices, MAX_CHOICES } from '../../frontend/js/features/reportTargets.js';

const id = (n) => n.toString(16).padStart(32, '0');
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', '..');

test('only the other person\'s messages are offered, newest first', () => {
  const msgs = [{ id: id(1), mine: false, body: 'first' }, { id: id(2), mine: true, body: 'my reply' }, { id: id(3), mine: false, body: 'third' }];
  assert.deepEqual(reportChoices(msgs).map((c) => c.id), [id(3), id(1)]);
});

test('choices are capped, previews are one short line, bad ids are dropped', () => {
  const many = Array.from({ length: 50 }, (_, i) => ({ id: id(i + 1), mine: false, body: `msg ${i}` }));
  assert.equal(reportChoices(many).length, MAX_CHOICES);
  const [c] = reportChoices([{ id: id(9), mine: false, body: 'line one\n\n  line two ' + 'x'.repeat(200) }]);
  assert.ok(c.label.length <= 60 && !c.label.includes('\n') && c.label.endsWith('…'));
  assert.deepEqual(reportChoices([{ id: '../x', mine: false, body: 'a' }, { id: 5, mine: false, body: 'b' }, null]), []);
  assert.equal(reportChoices([{ id: id(1), mine: false, body: '   ' }])[0].label, '(empty message)');
});

test('report dialog builds the menu with DOM APIs only and sends the chosen message id', () => {
  const page = fs.readFileSync(path.join(root, 'frontend/js/messages-page.js'), 'utf8');
  assert.ok(!/innerHTML/.test(page));
  assert.match(page, /report\(current\.id, picked\.reason, picked\.messageId\)/);
  assert.match(fs.readFileSync(path.join(root, 'frontend/messages.html'), 'utf8'), /id="dlg-target-select"/);
});

test('consent banner reserves page space while open and releases it on every choice', () => {
  const src = fs.readFileSync(path.join(root, 'frontend/js/features/consent.js'), 'utf8');
  assert.match(src, /classList\.add\('has-consent'\)/);
  assert.match(src, /classList\.remove\('has-consent'\)/);
  assert.match(src, /removeProperty\('--consent-h'\)/);
  assert.match(fs.readFileSync(path.join(root, 'frontend/css/consent.css'), 'utf8'), /body\.has-consent\{padding-bottom:var\(--consent-h/);
});
