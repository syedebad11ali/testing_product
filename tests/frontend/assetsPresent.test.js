import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

/* Regression guard: files the UI points at must exist, so a missing asset is a failing test, not a silent 404. */
const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const read = (rel) => readFileSync(join(ROOT, rel), 'utf8');

function walk(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? walk(join(dir, e.name)) : [join(dir, e.name)]));
}

test('every "Property Images/..." file referenced by the frontend exists under public/assets', () => {
  const refs = new Set();
  for (const f of walk(join(ROOT, 'frontend')).filter((p) => /\.(js|html|css)$/.test(p))) {
    for (const m of readFileSync(f, 'utf8').matchAll(/Property Images\/([^'"`)\\]+)/g)) refs.add(m[1].trim());
  }
  assert.ok(refs.size >= 16, `expected at least 16 references, found ${refs.size}`);
  const missing = [...refs].filter((r) => !existsSync(join(ROOT, 'public/assets/Property Images', decodeURIComponent(r))));
  assert.deepEqual(missing, []);
});

test('the sample-document folder the verification flow fetches from exists and has real files', () => {
  assert.match(read('frontend/js/config.js'), /SAMPLES_URL = 'assets\/samples\/'/);
  const dir = join(ROOT, 'public/assets/samples');
  const files = readdirSync(dir).filter((n) => /\.(png|jpe?g|pdf)$/i.test(n));
  assert.ok(files.length >= 20, `only ${files.length} sample files`);
  for (const n of files) assert.ok(statSync(join(dir, n)).size > 1000, `${n} looks empty`);
});

test('no secrets or owner-name datasets were brought over with the assets', () => {
  const all = walk(join(ROOT, 'public'));
  assert.deepEqual(all.filter((p) => /(^|[\\/])\.env($|\.)/.test(p) && !p.endsWith('.example')), []);
  assert.deepEqual(all.filter((p) => /users\.json$/.test(p)), []);
});
