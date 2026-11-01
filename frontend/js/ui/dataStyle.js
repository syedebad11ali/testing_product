/* ui/dataStyle.js — applies computed styles without inline style attributes (strict CSP, no 'unsafe-inline').
 *
 * Templates carry data, not CSS:   data-w="42"            -> el.style.width = "42%"
 *                                  data-bg="assets/a.jpg" -> el.style.setProperty('--img', 'url("assets/a.jpg")')
 * Writing through the CSSOM is allowed by CSP; inline style attributes written into markup are not. A MutationObserver applies the
 * values to anything added to the page (templates are rendered with innerHTML) before the browser paints it. */

export const clampPct = (value) => {
  const n = Number(value);
  return Number.isFinite(n) ? Math.min(100, Math.max(0, n)) : 0;
};

/** A safe CSS url() token for a plain URL/path (quotes, backslashes and line breaks are escaped). */
export const cssUrl = (value) => `url("${String(value).replace(/["\\\n\r\f]/g, (c) => (c === '"' || c === '\\' ? `\\${c}` : ' '))}")`;

/** Relative paths must be made absolute here: a url() inside a custom property resolves against the STYLESHEET
 * (/css/utilities.css), not the page, so "assets/x.jpg" would silently become /css/assets/x.jpg. */
export function resolveUrl(value, base) {
  try { return new URL(String(value), base || (typeof document !== 'undefined' ? document.baseURI : undefined)).href; } catch (_) { return String(value); }
}

export function applyDataStyle(el) {
  if (!el || el.nodeType !== 1 || !el.getAttribute) return;
  const w = el.getAttribute('data-w');
  if (w !== null) el.style.width = `${clampPct(w)}%`;
  const bg = el.getAttribute('data-bg');
  if (bg) el.style.setProperty('--img', cssUrl(resolveUrl(bg)));
}

export function applyDataStyles(root) {
  if (!root || !root.querySelectorAll) return;
  applyDataStyle(root);
  for (const el of root.querySelectorAll('[data-w],[data-bg]')) applyDataStyle(el);
}

export function initDataStyles(doc = document) {
  applyDataStyles(doc.body || doc.documentElement);
  if (typeof MutationObserver === 'undefined') return null;
  const observer = new MutationObserver((records) => {
    for (const r of records) for (const node of r.addedNodes) applyDataStyles(node);
  });
  observer.observe(doc.documentElement, { childList: true, subtree: true });
  return observer;
}
