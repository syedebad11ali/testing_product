/* features/featured.js — Featured Properties carousel on the home page (ported from the reference project's app.js).
 *
 * Differences from the original, required by this app's rules:
 *  - no inline style attributes, inline handlers or injected style elements: the look is in css/featured.css, actions are data-onclick
 *    (ui/actions.js), images use data-bg (ui/dataStyle.js), the progress duration is a CSS variable written through the CSSOM;
 *  - every interpolated value is escaped;
 *  - WCAG 2.2.2: a visible Pause/Play button, rotation also stops on hover/focus/hidden tab, and never runs when the visitor
 *    prefers reduced motion. Slide changes are announced politely only when the visitor changes slides or rotation is paused. */
import { escapeHtml } from '../core/html.js';
import { PROPERTIES } from '../data/properties.js';
import { state } from '../state/store.js';

/** Properties shown in the carousel, in order. Unknown ids are skipped; if none match, properties flagged `featured` are used. */
export const FEATURED_IDS = ['p1', 'p4', 'p8', 'p2'];
export const FEAT_AUTOPLAY_MS = 6000;   // 0 turns auto-rotation off
const SWIPE_PX = 45;

let timer = null;
let busy = false;
let generation = 0;         // lets an older animation's cleanup know it was superseded
let userPaused = false;     // the Pause button
let hoverPaused = false;    // pointer over / focus inside the carousel

export function featuredList(ids = FEATURED_IDS, all = PROPERTIES) {
  const list = ids.map((id) => all.find((p) => p.id === id)).filter(Boolean);
  return list.length ? list : all.filter((p) => p.featured);
}

/** Wrap-around index: -1 -> last, n -> 0. */
export const wrapIndex = (i, n) => (n > 0 ? ((i % n) + n) % n : 0);

const reducedMotion = () => typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
const autoplayAllowed = () => FEAT_AUTOPLAY_MS > 0 && featuredList().length > 1 && !reducedMotion();

const SAFE_ID = /^[A-Za-z0-9_-]{1,40}$/;

export function featuredCardHTML(f, index = 0, total = 1) {
  const open = SAFE_ID.test(String(f.id)) ? ` data-onclick="nav('detail','${f.id}')"` : '';   // ids come from our data; anything odd gets no click action
  const chips = [
    f.size ? `<span class="fc-chip">${escapeHtml(f.size)}</span>` : '',
    f.beds ? `<span class="fc-chip">${escapeHtml(f.beds)} Beds</span>` : '',
    f.baths ? `<span class="fc-chip">${escapeHtml(f.baths)} Baths</span>` : '',
    f.type ? `<span class="fc-chip">${escapeHtml(f.type)}</span>` : '',
  ].join('');
  return `
    <article class="fc-card" role="group" aria-roledescription="slide" aria-label="${index + 1} of ${total}: ${escapeHtml(f.title)}" ${open}>
      <div class="fc-media bg-photo bg-grad-feat" data-bg="${escapeHtml(f.image)}" role="img" aria-label="${escapeHtml(f.title)} in ${escapeHtml(f.area)}">
        <span class="fc-tag">&#9733; Featured</span>
      </div>
      <div class="fc-body">
        <h3 class="fc-title">${escapeHtml(f.title)}</h3>
        <div class="fc-loc">${escapeHtml(f.area)}, Karachi</div>
        <div class="fc-price">${escapeHtml(f.priceLabel)}</div>
        <div class="fc-chips">${chips}</div>
        <div class="fc-foot">
          <span class="fc-verif">&#10003; Verified</span>
          <button class="fc-cta" type="button" aria-label="View ${escapeHtml(f.title)}">View Property &rarr;</button>
        </div>
      </div>
    </article>`;
}

export function featuredDotsHTML(n, active) {
  const dots = Array.from({ length: n }, (_, i) =>
    `<button class="fc-dot${i === active ? ' active' : ''}" type="button" aria-label="Show featured property ${i + 1} of ${n}"${i === active ? ' aria-current="true"' : ''} data-onclick="featGo(${i})"><i></i></button>`).join('');
  return `${dots}<span class="fc-count" aria-hidden="true">${active + 1} / ${n}</span>`;
}

/** The whole carousel section (markup only; call initFeatured() after it is in the DOM). */
export function renderFeatured() {
  const list = featuredList();
  if (!list.length) return '';
  if (state.featIdx >= list.length || state.featIdx < 0) state.featIdx = 0;
  const many = list.length > 1;
  const pause = many && autoplayAllowed()
    ? `<button class="fc-pause" id="fcPause" type="button" aria-pressed="${userPaused}" data-onclick="featToggle()">${userPaused ? 'Play' : 'Pause'}<span class="sr-only"> automatic rotation</span></button>` : '';
  return `
    <div class="section-title" id="fcHeading">Featured Properties</div>
    <section class="fc-root${userPaused ? ' paused' : ''}" id="fcRoot" role="region" aria-roledescription="carousel" aria-labelledby="fcHeading">
      <div class="fc-wrap" id="fcWrap">
        ${many ? '<button class="fc-btn" type="button" aria-label="Previous featured property" data-onclick="featMove(-1)">&#8249;</button>' : ''}
        <div class="fc-slot" id="fcSlot" aria-live="off">${featuredCardHTML(list[state.featIdx], state.featIdx, list.length)}</div>
        ${many ? '<button class="fc-btn" type="button" aria-label="Next featured property" data-onclick="featMove(1)">&#8250;</button>' : ''}
      </div>
      ${many ? `<div class="fc-dots" id="fcDots">${featuredDotsHTML(list.length, state.featIdx)}${pause}</div>` : ''}
    </section>`;
}

function setLive(polite) {
  const slot = document.getElementById('fcSlot');
  if (slot) slot.setAttribute('aria-live', polite ? 'polite' : 'off');
}

/** Go to slide ``i`` (wraps). ``dir`` is +1/-1 for the slide direction; ``user`` marks a visitor-initiated change (announced). */
export function featGo(i, dir, user = true) {
  const list = featuredList();
  const slot = document.getElementById('fcSlot'), dots = document.getElementById('fcDots');
  if (!slot || list.length < 2) return;
  if (busy) { slot.getAnimations?.().forEach((a) => a.cancel()); busy = false; }   // a quick second click interrupts the animation instead of being lost
  const n = list.length, from = state.featIdx, to = wrapIndex(i, n);
  if (to === from) return;
  dir = dir || (to > from ? 1 : -1);
  state.featIdx = to;
  setLive(user || userPaused);
  const apply = () => { slot.innerHTML = featuredCardHTML(list[to], to, n); };
  const card = slot.firstElementChild;
  if (card && card.animate && !reducedMotion()) {
    busy = true;
    const mine = ++generation;
    const release = () => { if (generation === mine) busy = false; };
    setTimeout(release, 700);                      // never stay locked if an animation event is lost (background tab)
    card.animate([{ opacity: 1, transform: 'translateX(0)' }, { opacity: 0, transform: `translateX(${-40 * dir}px)` }], { duration: 170, easing: 'ease-in', fill: 'forwards' })
      .onfinish = () => {
        apply();
        const next = slot.firstElementChild;
        if (next && next.animate) next.animate([{ opacity: 0, transform: `translateX(${40 * dir}px)` }, { opacity: 1, transform: 'translateX(0)' }], { duration: 240, easing: 'ease-out' }).onfinish = release;
        else release();
      };
  } else apply();
  if (dots) dots.innerHTML = featuredDotsHTML(n, to) + (document.getElementById('fcPause') ? pauseButtonHTML() : '');
  restartAuto();
}

const pauseButtonHTML = () =>
  `<button class="fc-pause" id="fcPause" type="button" aria-pressed="${userPaused}" data-onclick="featToggle()">${userPaused ? 'Play' : 'Pause'}<span class="sr-only"> automatic rotation</span></button>`;

export const featMove = (d) => featGo(state.featIdx + d, d);

function stopAuto() { clearInterval(timer); timer = null; }

function restartAuto() {
  stopAuto();
  const root = document.getElementById('fcRoot');
  if (root) root.classList.toggle('paused', userPaused || hoverPaused);
  if (!autoplayAllowed() || userPaused || hoverPaused || document.hidden) return;
  timer = setInterval(() => {
    if (!document.getElementById('fcSlot')) { stopAuto(); return; }   // left the home page
    featGo(state.featIdx + 1, 1, false);
  }, FEAT_AUTOPLAY_MS);
}

/** Pause / Play button. */
export function featToggle() {
  userPaused = !userPaused;
  const btn = document.getElementById('fcPause');
  if (btn) { btn.setAttribute('aria-pressed', String(userPaused)); btn.firstChild.textContent = userPaused ? 'Play' : 'Pause'; }
  setLive(userPaused);
  restartAuto();
}

/** Wire hover/focus pause, arrow keys and swipe. Idempotent per rendered carousel; call after every home render. */
export function initFeatured() {
  const wrap = document.getElementById('fcWrap'), root = document.getElementById('fcRoot');
  if (!wrap || !root) { stopAuto(); return; }
  if (wrap.dataset.ready) return;
  wrap.dataset.ready = '1';
  root.style.setProperty('--fc-ms', `${FEAT_AUTOPLAY_MS}ms`);       // CSSOM write: allowed by the strict CSP
  root.addEventListener('mouseenter', () => { hoverPaused = true; restartAuto(); });
  root.addEventListener('mouseleave', () => { hoverPaused = false; restartAuto(); });
  root.addEventListener('focusin', () => { hoverPaused = true; restartAuto(); });
  root.addEventListener('focusout', (e) => { if (!root.contains(e.relatedTarget)) { hoverPaused = false; restartAuto(); } });
  root.addEventListener('keydown', (e) => { if (e.key === 'ArrowLeft') featMove(-1); else if (e.key === 'ArrowRight') featMove(1); });
  let x0 = null;                                                   // swipe on touch screens
  wrap.addEventListener('touchstart', (e) => { x0 = e.touches[0].clientX; }, { passive: true });
  wrap.addEventListener('touchend', (e) => {
    if (x0 === null) return;
    const dx = e.changedTouches[0].clientX - x0; x0 = null;
    if (Math.abs(dx) > SWIPE_PX) featMove(dx < 0 ? 1 : -1);
  });
  if (!initFeatured.visibilityBound) {
    initFeatured.visibilityBound = true;
    document.addEventListener('visibilitychange', restartAuto);    // no rotation in a background tab
  }
  hoverPaused = false;
  restartAuto();
}
