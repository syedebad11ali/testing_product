/* Every data-on* action used in templates must be registered in ui/actions.js, and no inline
 * on*="" attribute may remain (a strict CSP would silently break it). */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { installDom } from './helpers/domStub.js';

installDom();
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', '..', 'frontend');
const { ACTIONS } = await import('../../frontend/js/ui/actions.js');
const { parseCalls, dispatch } = await import('../../frontend/js/ui/dispatch.js');

function walk(dir) { return fs.readdirSync(dir, { withFileTypes: true }).flatMap(e => e.isDirectory() ? walk(path.join(dir, e.name)) : [path.join(dir, e.name)]); }
const sources = [...walk(path.join(root, 'js')), ...fs.readdirSync(root).filter(f => f.endsWith('.html')).map(f => path.join(root, f))];
const BUILTINS = new Set(['stopPropagation', 'preventDefault']);

test('every data-on* call resolves to a registered action', () => {
  const missing = new Set();
  let attrs = 0;
  for (const file of sources) {
    for (const m of fs.readFileSync(file, 'utf8').matchAll(/\bdata-on(?:click|change|input|keydown|submit)="([^"]*)"/g)) {
      attrs++;
      const code = m[1].replace(/\$\{[^}]*\}/g, ' ');
      for (const c of code.matchAll(/(?<![\w$.])([A-Za-z_$][\w$]*)\(/g)) {
        if (!BUILTINS.has(c[1]) && typeof ACTIONS[c[1]] !== 'function') missing.add(`${c[1]} (${path.relative(root, file)})`);
      }
    }
  }
  assert.ok(attrs > 60, `expected to scan ~90 handler attributes, found ${attrs}`);
  assert.deepEqual([...missing], []);
});

test('no inline on*="" event attributes remain (strict CSP)', () => {
  const offenders = [];
  for (const file of sources.filter(f => !f.includes('dispatch.js'))) {
    for (const m of fs.readFileSync(file, 'utf8').matchAll(/(?<![-\w.])on(?:click|change|input|keydown|submit|load|error|mouse\w+)=["']/g)) offenders.push(`${path.relative(root, file)}: ${m[0]}`);
  }
  assert.deepEqual(offenders, []);
});

test('parser reads literals, this/this.value/event and multiple calls', () => {
  assert.deepEqual(parseCalls("nav('detail','DEMO-1');closeDrawer();").map(c => c.name), ['nav', 'closeDrawer']);
  const [c] = parseCalls(`docStartSample('a b','x',true,null,-3,this.value,this,event)`);
  assert.deepEqual(c.args.map(a => a.k), ['lit', 'lit', 'lit', 'lit', 'lit', 'value', 'this', 'event']);
  assert.equal(c.args[0].v, 'a b');
});

test('parser rejects anything that is not a plain action call', () => {
  for (const bad of ["alert(document.cookie)||x", "a(b)", "a(this.innerHTML)", "x=1", "fn('unterminated", "a();b", "a() b()", "a(1 2)"]) {
    if (bad === "alert(document.cookie)||x") assert.throws(() => parseCalls(bad), SyntaxError, bad);
    else assert.throws(() => parseCalls(bad), SyntaxError, bad);
  }
});

const el = (attrs, parent = null, extra = {}) => ({ getAttribute: k => attrs[k] ?? null, parentElement: parent, ...extra });

test('dispatch calls allow-listed actions with resolved arguments', () => {
  const seen = [];
  const actions = { go: (...a) => seen.push(a), sink: (v) => seen.push(v) };
  const target = el({ 'data-onclick': "go('x',2);sink(this.value)" }, null, { value: 'typed' });
  dispatch(actions, 'click', { target });
  assert.deepEqual(seen, [['x', 2], 'typed']);
});

test('dispatch ignores unknown names and prototype keys (no code execution)', () => {
  const calls = [];
  const orig = console.error; console.error = () => {};
  try { dispatch({ ok: () => calls.push('ok') }, 'click', { target: el({ 'data-onclick': "constructor('x');toString();ok()" }) }); } finally { console.error = orig; }
  assert.deepEqual(calls, ['ok']);
});

test('stopPropagation() stops outer handlers, like the inline version did', () => {
  const seen = [];
  const actions = { inner: () => seen.push('inner'), outer: () => seen.push('outer') };
  const parent = el({ 'data-onclick': 'outer()' });
  dispatch(actions, 'click', { target: el({ 'data-onclick': 'stopPropagation();inner()' }, parent) });
  assert.deepEqual(seen, ['inner']);
  seen.length = 0;
  dispatch(actions, 'click', { target: el({ 'data-onclick': 'inner()' }, parent) });
  assert.deepEqual(seen, ['inner', 'outer']);
});

test('preventDefault() builtin calls the event method', () => {
  let prevented = false;
  dispatch({ f: () => {} }, 'submit', { target: el({ 'data-onsubmit': 'preventDefault();f()' }), preventDefault() { prevented = true; } });
  assert.ok(prevented);
});
