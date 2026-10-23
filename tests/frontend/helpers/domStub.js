/* Minimal browser stub so UI modules can be imported and rendered in plain Node.
 * It is deliberately dumb: elements record innerHTML/classList/attributes and nothing more. */
const makeEl = (id = '') => {
  const el = {
    id, innerHTML: '', textContent: '', className: '', dataset: {}, style: {}, children: [], value: '',
    classList: { _s: new Set(), add(c){this._s.add(c);}, remove(c){this._s.delete(c);}, toggle(c, f){ (f===undefined ? !this._s.has(c) : f) ? this._s.add(c) : this._s.delete(c); }, contains(c){return this._s.has(c);} },
    setAttribute(k, v){ this[k] = v; }, getAttribute(k){ return this[k]; },
    appendChild(c){ this.children.push(c); return c; }, remove(){}, addEventListener(){}, removeEventListener(){},
    querySelector(){ return null; }, querySelectorAll(){ return []; }, scrollIntoView(){}, focus(){},
  };
  return el;
};
export function installDom() {
  const byId = new Map();
  const doc = {
    documentElement: makeEl('html'), body: makeEl('body'), head: makeEl('head'),
    getElementById(id){ if(!byId.has(id)) byId.set(id, makeEl(id)); return byId.get(id); },
    createElement(){ return makeEl(); }, querySelector(){ return null; }, querySelectorAll(){ return []; },
    addEventListener(){},
  };
  const store = (() => { const m = new Map(); return { getItem:k=>m.has(k)?m.get(k):null, setItem:(k,v)=>m.set(k,String(v)), removeItem:k=>m.delete(k) }; })();
  const win = { scrollTo(){}, addEventListener(){}, location: { hash: '' }, print(){} };
  Object.assign(globalThis, { document: doc, window: Object.assign(globalThis.window || {}, win), localStorage: store, sessionStorage: (() => { const m = new Map(); return { getItem:k=>m.has(k)?m.get(k):null, setItem:(k,v)=>m.set(k,String(v)), removeItem:k=>m.delete(k) }; })() });
  try { Object.defineProperty(globalThis, 'navigator', { value: {}, configurable: true }); } catch (_) {}
  return { document: doc, byId };
}
