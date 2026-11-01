/* ui/dispatch.js — CSP-safe replacement for inline `onclick="…"` attributes.
 *
 * Templates carry `data-onclick="nav('home')"` (also data-oninput / data-onchange /
 * data-onsubmit / data-onkeydown). ONE delegated listener per event type reads the attribute,
 * parses it with the tiny grammar below (never eval) and calls an allow-listed action.
 *
 * Grammar:  call (';' call)* [';']      call := name '(' [arg (',' arg)*] ')'
 *           arg := 'string' | "string" | number | true | false | null | this | this.value | event
 * Anything else is rejected and logged; unknown action names are ignored. */

/** @typedef {{name:string,args:Array<{k:string,v?:any}>}} Call */

const IDENT = /[A-Za-z_$][\w$]*/y;
const NUMBER = /-?\d+(?:\.\d+)?/y;

/** Parse an attribute value into calls. @param {string} src @returns {Call[]} @throws {SyntaxError} */
export function parseCalls(src) {
  const s = String(src);
  let i = 0;
  const ws = () => { while (i < s.length && /\s/.test(s[i])) i++; };
  const fail = (m) => { throw new SyntaxError(`${m} at ${i} in "${s}"`); };
  const match = (re) => { re.lastIndex = i; const m = re.exec(s); if (m) i += m[0].length; return m && m[0]; };
  function arg() {
    ws();
    const q = s[i];
    if (q === "'" || q === '"') {
      let out = ''; i++;
      while (i < s.length && s[i] !== q) { if (s[i] === '\\') i++; out += s[i++]; }
      if (s[i] !== q) fail('Unterminated string');
      i++; return { k: 'lit', v: out };
    }
    const n = match(NUMBER);
    if (n !== null) return { k: 'lit', v: Number(n) };
    const id = match(IDENT);
    if (id === 'true' || id === 'false') return { k: 'lit', v: id === 'true' };
    if (id === 'null') return { k: 'lit', v: null };
    if (id === 'undefined') return { k: 'lit', v: undefined };
    if (id === 'event') return { k: 'event' };
    if (id === 'this') { if (s[i] === '.') { i++; if (match(IDENT) !== 'value') fail('Only this.value is allowed'); return { k: 'value' }; } return { k: 'this' }; }
    return fail('Unexpected argument');
  }
  const calls = [];
  ws();
  while (i < s.length) {
    const name = match(IDENT); if (!name) fail('Expected action name');
    ws(); if (s[i] !== '(') fail('Expected (');
    i++; ws();
    const args = [];
    if (s[i] !== ')') { for (;;) { args.push(arg()); ws(); if (s[i] === ',') { i++; continue; } break; } }
    if (s[i] !== ')') fail('Expected )');
    i++; calls.push({ name, args }); ws();
    if (s[i] === ';') { i++; ws(); } else if (i < s.length) fail('Expected ;');
  }
  return calls;
}

const EVENTS = ['click', 'input', 'change', 'submit', 'keydown'];

/** Run the actions for one event, walking from the target up so nested handlers behave like inline ones.
 * @param {Record<string,Function>} actions @param {string} type @param {Event} event */
export function dispatch(actions, type, event) {
  const ctx = { stopped: false };
  const builtins = {
    stopPropagation() { ctx.stopped = true; },
    preventDefault() { if (event.preventDefault) event.preventDefault(); },
  };
  for (let el = event.target; el && el.getAttribute; el = el.parentElement) {
    const code = el.getAttribute(`data-on${type}`);
    if (!code) continue;
    let calls;
    try { calls = parseCalls(code); } catch (e) { console.error('[kpt] bad handler', e.message); continue; }
    for (const { name, args } of calls) {
      const fn = Object.hasOwn(builtins, name) ? builtins[name] : Object.hasOwn(actions, name) ? actions[name] : null;
      if (!fn) { console.error(`[kpt] unknown action "${name}"`); continue; }
      const values = args.map(a => a.k === 'lit' ? a.v : a.k === 'event' ? event : a.k === 'value' ? el.value : el);
      try { fn(...values); } catch (e) { console.error(`[kpt] action "${name}" failed`, e); }
    }
    if (ctx.stopped) break;
  }
}

/** Attach one delegated listener per event type. @param {Document} root @param {Record<string,Function>} actions */
export function installDispatcher(root, actions) {
  for (const type of EVENTS) root.addEventListener(type, (event) => dispatch(actions, type, event));
}
