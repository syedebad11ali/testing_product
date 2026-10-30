import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';

/* Guards the strict-style pages: pages listed in backend/security/headers.py STRICT_STYLE_PATHS are served WITHOUT
 * style-src 'unsafe-inline'. If any of them (or any module they load) gains inline style markup, this fails. */
// fileURLToPath, NOT URL#pathname: on Windows .pathname is "/C:/Users/..." and join()/readFileSync turn that into "C:\C:\Users\...".
const FE = fileURLToPath(new URL('../../frontend/', import.meta.url));
const PAGES = { index: 'index.html', login: 'login.html', admin: 'admin.html', privacy: 'privacy.html', messages: 'messages.html', listings: 'listings.html', 'nice-try': 'nice-try.html', 'chatbot-demo': 'widget/demo.html', 404: '404.html' };

/* Markup/strings that CSP style-src blocks. Plain CSSOM writes (el.style.width = …, setProperty) are allowed and not matched. */
export const INLINE_STYLE_PATTERNS = [
  [/\sstyle\s*=\s*\\?["']/i, 'style="…" attribute'],
  [/<style[\s>]/i, '<style> block'],
  [/setAttribute\(\s*['"]style['"]/i, "setAttribute('style')"],
  [/\.cssText\b/, 'style.cssText'],
  [/\.style\s*=\s*[`'"]/, 'style = "string"'],
  [/\.attributes?\.style\b/, 'attribute style'],
];

export function findInlineStyle(source) {
  return INLINE_STYLE_PATTERNS.filter(([re]) => re.test(source)).map(([, name]) => name);
}

function resolveImport(from, spec) {
  if (!/^\.{1,2}\//.test(spec)) return null; // bare/remote specifiers are not ours
  const p = normalize(join(dirname(from), spec));
  return existsSync(p) ? p : null;
}

function graph(entries) {
  const seen = new Set(); const queue = [...entries];
  while (queue.length) {
    const file = queue.pop();
    if (seen.has(file)) continue;
    seen.add(file);
    const src = readFileSync(file, 'utf8');
    for (const m of src.matchAll(/(?:import|export)\s[^'"`]*?from\s*['"]([^'"]+)['"]|import\(\s*['"]([^'"]+)['"]\s*\)|import\s*['"]([^'"]+)['"]/g)) {
      const next = resolveImport(file, m[1] || m[2] || m[3]);
      if (next) queue.push(next);
    }
  }
  return [...seen];
}

const scriptsOf = (html) => [...html.matchAll(/<script[^>]*\ssrc=["']([^"']+)["']/gi)].map((m) => m[1]).filter((s) => !/^https?:/.test(s))
  .map((s) => join(FE, s.replace(/^\//, '').replace(/^static\//, 'widget/')));  // /static/chatbot.js is served from frontend/widget/

test('the scanner flags the markup CSP blocks and ignores CSSOM writes', () => {
  assert.deepEqual(findInlineStyle('<div style="color:red">'), ['style="…" attribute']);
  assert.deepEqual(findInlineStyle("`<b style=\\\"x\\\">`"), ['style="…" attribute']);
  assert.ok(findInlineStyle("el.setAttribute('style','a:b')").length);
  assert.ok(findInlineStyle('el.style.cssText = "a:b"').length);
  assert.deepEqual(findInlineStyle("el.style.width = `${n}%`; el.style.setProperty('--x','1')"), []);
});

for (const [name, file] of Object.entries(PAGES)) {
  test(`strict-style page "${name}": HTML and every module it loads have no inline style markup`, () => {
    const htmlPath = join(FE, file);
    const html = readFileSync(htmlPath, 'utf8');
    assert.deepEqual(findInlineStyle(html), [], `${file} itself`);
    const files = graph(scriptsOf(html));
    assert.ok(name === '404' || files.length > 0, 'page should load at least one script');
    for (const f of files) assert.deepEqual(findInlineStyle(readFileSync(f, 'utf8')), [], f.replace(FE, ''));
  });
}

test('every path in STRICT_STYLE_PATHS is covered by a page checked above', () => {
  const py = readFileSync(new URL('../../backend/security/headers.py', import.meta.url), 'utf8');
  const block = /STRICT_STYLE_PATHS = frozenset\(\{([\s\S]*?)\}\)/.exec(py)[1];
  const paths = [...block.matchAll(/"(\/[^"]*)"/g)].map((m) => m[1]);
  assert.ok(paths.length >= 10);
  for (const p of paths) {
    const key = p.replace(/^\//, '').replace(/\.html$/, '') || 'index';
    const covered = key === 'signup' ? 'login' : key;
    assert.ok(PAGES[covered], `${p} has no inline-style check`);
  }
});

test('every utility / tone / background class used by the app templates is defined in utilities.css', () => {
  const css = readFileSync(join(FE, 'css/utilities.css'), 'utf8');
  const defined = new Set([...css.matchAll(/\.([A-Za-z][\w-]*)/g)].map((m) => m[1]));
  const files = graph([join(FE, 'js/main.js')]);
  let used = 0;
  for (const f of files) {
    for (const m of readFileSync(f, 'utf8').matchAll(/\b(u-[a-z0-9-]+|bg-photo|bg-grad-[a-z]+)\b/g)) {
      used += 1;
      assert.ok(defined.has(m[1]), `${m[1]} used in ${f.replace(FE, '')} but not defined`);
    }
  }
  assert.ok(used > 50, 'expected the migrated templates to use utility classes');
  for (const tone of ['ok', 'bad', 'warn', 'mute']) assert.ok(defined.has(`tone-${tone}`), tone);
});

test('index.html loads utilities.css after the component sheets', () => {
  const html = readFileSync(join(FE, 'index.html'), 'utf8');
  assert.ok(html.indexOf('css/utilities.css') > html.indexOf('css/components.css'));
});
