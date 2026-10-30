import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

/* Windows guard: a file:// URL's `.pathname` is "/C:/Users/..." on Windows, which breaks path.join()/fs (it becomes "C:\\C:\\Users\\...").
 * Tests must convert file URLs with fileURLToPath() or pass the URL object itself to fs. */
const dir = dirname(fileURLToPath(import.meta.url));

test('no test turns import.meta.url into a path with URL#pathname', () => {
  for (const f of readdirSync(dir).filter((n) => n.endsWith('.js'))) {
    if (f === 'portablePaths.test.js') continue;
    const src = readFileSync(join(dir, f), 'utf8');
    assert.ok(!/new URL\([^)]*import\.meta\.url\)\s*\.pathname/.test(src), `${f} uses URL#pathname for a file path`);
    assert.ok(!/import\.meta\.url[^;\n]*\.pathname/.test(src), `${f} uses .pathname on import.meta.url`);
  }
});

test('fileURLToPath yields a path fs can read', () => {
  const p = fileURLToPath(new URL('../../frontend/', import.meta.url));
  assert.ok(readdirSync(p).includes('index.html'));
});
