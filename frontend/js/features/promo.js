/* features/promo.js — Floating promo banner (timing, cooldown, dismissal). */
import { BANNER_COOLDOWN_MS, STORAGE_KEYS } from '../config.js';
import { session } from '../core/storage.js';
import { PROPERTIES } from '../data/properties.js';
import { promoRuntime } from '../state/store.js';

function pickPromoProperty(excludeId){
  const pool = PROPERTIES.filter(p=>!p.featured && p.id!==excludeId);
  return pool.length ? pool[Math.floor(Math.random()*pool.length)] : null;
}

function renderPromo(p){
  document.getElementById('promo').innerHTML = `
    <div class="promo-inner">
      <div class="promo-thumb"><span class="badge">BEST PRICE</span></div>
      <div class="promo-body">
        <button class="promo-close" onclick="hidePromo()" aria-label="Dismiss">✕</button>
        <div class="pt">${p.title} · ${p.type}</div>
        <div class="pl">${p.area}, Karachi</div>
        <div class="pp">${p.priceLabel} <span class="good-deal">· Good Deal</span></div>
        <button onclick="hidePromo(true);nav('detail','${p.id}')">View Property</button>
      </div>
    </div>`;
}

function revealPromo(p){
  if(!p) return;
  promoRuntime.lastId = p.id;
  renderPromo(p);
  const el = document.getElementById('promo');
  el.classList.remove('hidden');
  el.classList.add('show');
}

// Called on load, and again once a cooldown finishes without a fresh pick queued.
export function showPromo(){
  const lastClosed = Number(session.getRaw(STORAGE_KEYS.bannerClosedAt, 0));
  const remaining = BANNER_COOLDOWN_MS - (Date.now() - lastClosed);
  if(lastClosed && remaining > 0){
    // User closed it recently (even in a previous page load this session) -
    // stay hidden until the full cooldown has actually elapsed.
    clearTimeout(promoRuntime.timer);
    promoRuntime.timer = setTimeout(showPromo, remaining);
    return;
  }
  revealPromo(pickPromoProperty(promoRuntime.lastId));
}

// navigating=true when the user tapped "View Property" rather than the (X) -
// that's an accepted action, not a dismiss, so it doesn't start a cooldown.
export function hidePromo(navigating){
  const el = document.getElementById('promo');
  el.classList.remove('show');
  el.classList.add('hidden');
  if(navigating) return;

  session.setRaw(STORAGE_KEYS.bannerClosedAt, Date.now());
  const next = pickPromoProperty(promoRuntime.lastId);
  clearTimeout(promoRuntime.timer);
  promoRuntime.timer = setTimeout(()=>revealPromo(next), BANNER_COOLDOWN_MS);
}
