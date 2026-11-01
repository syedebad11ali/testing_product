/* features/home.js — Home screen: featured properties, area chips, search/filter/sort, property cards. */
import { escapeHtml } from '../core/html.js';
import { AREAS, DEMO_PROPERTY_DISPLAY_STATUS, PROPERTIES } from '../data/properties.js';
import { renderFeatured } from './featured.js';
import { loadHomeFilters, saveHomeFilters } from './homePrefs.js';
import { state } from '../state/store.js';
import { isAccountUser, loadSessionUser } from '../services/sessionUser.js';
import { showLoginRequired } from './loginPrompt.js';
import { toggleFavorite } from './favorites.js';

export function scrollToGrid(){ setTimeout(()=>{ const g=document.getElementById('grid'); if(g) g.scrollIntoView({behavior:'smooth'}); }, 60); }

/* --- HOME --- */
export function renderHome(){
  let list = PROPERTIES.filter(p=>{
    if(state.areaFilter && p.area!==state.areaFilter) return false;
    if(state.typeFilter && p.type!==state.typeFilter) return false;
    if(state.search){
      const s = state.search.toLowerCase();
      if(!(p.title.toLowerCase().includes(s)||p.area.toLowerCase().includes(s)||p.type.toLowerCase().includes(s))) return false;
    }
    return true;
  });
  if(state.sort==='low') list = list.slice().sort((a,b)=>a.price-b.price);
  if(state.sort==='high') list = list.slice().sort((a,b)=>b.price-a.price);
  if(state.sort==='large') list = list.slice().sort((a,b)=>parseFloat(b.size)-parseFloat(a.size));

  const areaChips = AREAS.map(a=>`<button class="area-chip ${state.areaFilter===a?'active':''}" data-onclick="setArea('${a}')">${a}</button>`).join('');
  const cards = list.map(p=>propCard(p)).join('') || `<div class="empty">No properties match these filters.<br>Try clearing a filter.</div>`;
  const listTitle = state.areaFilter ? `Properties in ${state.areaFilter}` : 'Property Listings';

  return `
  <div class="header">
    <div class="brand-block">
      <div class="eyebrow-home">Karachi Property Trust</div>
      <div class="brand" role="heading" aria-level="1">Find verified properties in Karachi</div>
      <div class="tagline">Search, verify and explore with confidence. Check a document or owner before you rely on it.</div>
    </div>
    <div class="search-bar">
      <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>
      <input placeholder="Search area, house, plot or property..." value="${escapeHtml(state.search)}" data-oninput="setSearch(this.value)">
    </div>
    <ul class="trust-chips" aria-label="What we check">
      <li>Document verification</li><li>Owner checks</li><li>AI assistant</li>
    </ul>
  </div>
  <main>
    ${renderFeatured()}

    <div class="doc-banner">
      <div class="icon">📄</div>
      <div class="txt"><h4>Have a document?</h4><p>Check your property document before relying on it.</p></div>
      <button data-onclick="openVerifyDocument()">Verify Your Document</button>
    </div>

    <div class="section-title">Browse by Area</div>
    <div class="areas">${areaChips}${state.areaFilter?`<button class="area-chip" data-onclick="setArea(null)">Clear</button>`:''}</div>

    <div class="section-title" id="listTitle">${listTitle}</div>
    <div class="filters-row">
      <select data-onchange="setTypeFilter(this.value)" aria-label="Filter by property type">
        <option value="">All types</option>
        ${[...new Set(PROPERTIES.map(p=>p.type))].map(t=>`<option ${state.typeFilter===t?'selected':''}>${t}</option>`).join('')}
      </select>
      <select data-onchange="setSort(this.value)" aria-label="Sort properties">
        <option value="newest" ${state.sort==='newest'?'selected':''}>Newest</option>
        <option value="low" ${state.sort==='low'?'selected':''}>Price: Low to High</option>
        <option value="high" ${state.sort==='high'?'selected':''}>Price: High to Low</option>
        <option value="large" ${state.sort==='large'?'selected':''}>Largest Property</option>
      </select>
    </div>
    <div class="grid" id="grid">${cards}</div>

    <div class="cta">
      <h3>Already have a property in mind?</h3>
      <p>Check its documents, ownership, legal status and utility clearance before you buy.</p>
      <button class="btn btn-primary" data-onclick="scrollToGrid()">Start a Verification</button>
    </div>
  </main>`;
}

export function renderList(){
  document.getElementById('listTitle').textContent = state.areaFilter?`Properties in ${state.areaFilter}`:'Property Listings';
  let list = PROPERTIES.filter(p=>{
    if(state.areaFilter && p.area!==state.areaFilter) return false;
    if(state.typeFilter && p.type!==state.typeFilter) return false;
    if(state.search){
      const s = state.search.toLowerCase();
      if(!(p.title.toLowerCase().includes(s)||p.area.toLowerCase().includes(s)||p.type.toLowerCase().includes(s))) return false;
    }
    return true;
  });
  if(state.sort==='low') list = list.slice().sort((a,b)=>a.price-b.price);
  if(state.sort==='high') list = list.slice().sort((a,b)=>b.price-a.price);
  if(state.sort==='large') list = list.slice().sort((a,b)=>parseFloat(b.size)-parseFloat(a.size));
  document.getElementById('grid').innerHTML = list.map(p=>propCard(p)).join('') || `<div class="empty">No properties match these filters.</div>`;
}

/** Registered users and admins get the area / type / sort stored on their own account (G5.3c), applied once the session has resolved.
 *  Guests, signed-out and unresolved sessions get nothing. Resolves true when something was restored, so the caller can re-render. */
export function initHomeFilters(){ return loadHomeFilters(state, AREAS, [...new Set(PROPERTIES.map(p=>p.type))]); }

export function setArea(a){ state.areaFilter=a; saveHomeFilters(state); renderList(); document.querySelectorAll('.area-chip').forEach(c=>c.classList.remove('active')); if(a) event.target.classList.add('active'); }

function propCard(p){
  const ov = DEMO_PROPERTY_DISPLAY_STATUS;
  const vtext = '✓ Verified';
  return `<div class="pcard">
    <div class="thumb bg-photo bg-grad-card" data-onclick="nav('detail','${p.id}')" data-bg="${p.image}">
      <button class="fav${state.saved.has(p.id)?' saved':''}" data-favorite-id="${p.id}" aria-pressed="${state.saved.has(p.id)}" aria-label="${state.saved.has(p.id)?'Remove from saved properties':'Save property'}" data-onclick="stopPropagation();toggleSave('${p.id}')"><span class="favorite-heart" data-favorite-heart aria-hidden="true">${state.saved.has(p.id)?'♥':'♡'}</span></button>
      <span class="type-tag">${p.type}</span>
    </div>
    <div class="body">
      <div class="title">${p.title}</div>
      <div class="loc">${p.area}</div>
      <div class="price">${p.priceLabel}</div>
      <div class="size">${p.size}${p.beds?` · ${p.beds} Bed`:''}</div>
      <div class="vrow ${ov==='unchecked'?'mute':''}">${vtext}</div>
      <button class="viewbtn" data-onclick="nav('detail','${p.id}')">View Property</button>
    </div>
  </div>`;
}

/** G5.1: saving or removing a favorite needs an account. All three controls (home heart, detail heart, detail Save Property) call this,
 *  so the check lives here. It awaits the existing GET /auth/me; a guest, a signed-out visitor or a session that cannot be resolved gets
 *  the existing login dialog (returning to the current page) and state.saved is not touched. An authorised change is stored on the
 *  account by features/favorites.js (G5.2). Resolves true when the favorite was toggled. */
export async function toggleSave(id){
  let user = null;
  try { user = await loadSessionUser(); } catch { user = null; }
  if(!isAccountUser(user)){ showLoginRequired({ feature: 'Saved properties' }); return false; }
  return toggleFavorite(id);   // G5.2: the change is stored on the account first; the controls update only when the server confirmed it
}

/* Filter inputs (replace former inline `state.x=this.value` handlers). */
export function setSearch(value){ state.search = value; renderList(); }
export function setTypeFilter(value){ state.typeFilter = value; saveHomeFilters(state); renderList(); }
export function setSort(value){ state.sort = value; saveHomeFilters(state); renderList(); }
