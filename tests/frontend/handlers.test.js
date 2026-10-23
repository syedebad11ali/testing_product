/* Every inline handler used in templates must be published on `window` by ui/actions.js.
 * This is the safety net for the inline-attribute pattern: rename or delete a function and
 * this test fails instead of a button silently doing nothing. */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { installDom } from './helpers/domStub.js';

installDom();
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', '..', 'frontend');
await import('../../frontend/js/ui/actions.js');

function walk(dir) { return fs.readdirSync(dir, { withFileTypes: true }).flatMap(e => e.isDirectory() ? walk(path.join(dir, e.name)) : [path.join(dir, e.name)]); }
const sources = [...walk(path.join(root, 'js')), path.join(root, 'index.html')];
const BUILTINS = new Set(['stopPropagation', 'preventDefault', 'getElementById', 'toggle', 'scrollIntoView', 'print', 'classList']);

test('every inline handler call resolves to a registered action', () => {
  const missing = new Set();
  let attrs = 0;
  for (const file of sources) {
    const text = fs.readFileSync(file, 'utf8');
    for (const m of text.matchAll(/\bon(?:click|change|input|keydown|submit)="([^"]*)"/g)) {
      attrs++;
      const code = m[1].replace(/\$\{[^}]*\}/g, ' ');
      for (const c of code.matchAll(/(?<![\w$.])([A-Za-z_$][\w$]*)\(/g)) {
        if (BUILTINS.has(c[1])) continue;
        if (typeof window[c[1]] !== 'function') missing.add(`${c[1]} (${path.relative(root, file)})`);
      }
    }
  }
  assert.ok(attrs > 90, `expected to scan ~100 handler attributes, found ${attrs}`);
  assert.deepEqual([...missing], []);
});

test('handlers reached through ${} interpolation are registered too', () => {
  for (const name of ['openVerifyDocument', 'scrollToGrid', 'nav', 'closeDrawer', 'openChat']) {
    assert.equal(typeof window[name], 'function', name);
  }
});

test('templates no longer assign to globals from attributes', () => {
  const offenders = [];
  for (const file of sources) {
    const text = fs.readFileSync(file, 'utf8');
    for (const m of text.matchAll(/\bon\w+="([^"]*\b(?:state|ownerVerification\w*|ownerForecastYears)\s*[.\w]*\s*=[^=][^"]*)"/g)) offenders.push(m[1]);
  }
  assert.deepEqual(offenders, []);
});
