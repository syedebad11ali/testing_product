/* features/home.js — Home screen: featured properties, area chips, search/filter/sort, property cards. */
import { LOGO_URL } from '../config.js';
import { escapeHtml } from '../core/html.js';
import { AREAS, PROPERTIES } from '../data/properties.js';
import { overallStatus } from '../domain/propertyStatus.js';
import { state } from '../state/store.js';

export function scrollToGrid(){ setTimeout(()=>{ const g=document.getElementById('grid'); if(g) g.scrollIntoView({behavior:'smooth'}); }, 60); }

/* --- HOME --- */
export function renderHome(){
  const featured = PROPERTIES.find(p=>p.featured);
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

  const areaChips = AREAS.map(a=>`<button class="area-chip ${state.areaFilter===a?'active':''}" onclick="setArea('${a}')">${a}</button>`).join('');
  const cards = list.map(p=>propCard(p)).join('') || `<div class="empty">No properties match these filters.<br>Try clearing a filter.</div>`;
  const listTitle = state.areaFilter ? `Properties in ${state.areaFilter}` : 'Property Listings';

  return `
  <div class="header">
    <div class="header-top">
      <button class="icon-btn" onclick="openDrawer()"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 6h16M4 12h16M4 18h16"/></svg></button>
      <div class="logo-badge"><img src="${LOGO_URL}" alt="Karachi Property Trust"></div>
    </div>
    <div class="brand-block">
      <div class="brand">Karachi Property Trust</div>
      <div class="tagline">Verification &amp; Trust Management System</div>
    </div>
    <div class="search-bar">
      <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>
      <input placeholder="Search area, house, plot or property..." value="${escapeHtml(state.search)}" oninput="setSearch(this.value)">
    </div>
  </div>
  <main>
    <div class="section-title">Featured Property</div>
    <div class="featured" onclick="nav('detail','${featured.id}')">
      <div class="fplaceholder" style="background-image:linear-gradient(0deg,rgba(0,0,0,.24),rgba(0,0,0,.04)),url('${featured.image}');background-size:cover;background-position:center;"><span class="tag">Featured</span></div>
      <div class="featured-body">
        <div class="ftitle">${featured.title}</div>
        <div class="floc">${featured.area}, Karachi</div>
        <div class="fprice">${featured.priceLabel}</div>
        <div class="fmeta">${featured.size}</div>
        <div class="verif-pill">✓ Verification Available</div>
        <button class="btn btn-primary btn-block">View Property</button>
      </div>
    </div>

    <div class="doc-banner">
      <div class="icon">📄</div>
      <div class="txt"><h4>Have a document?</h4><p>Check your property document before relying on it.</p></div>
      <button onclick="openVerifyDocument()">Verify Your Document</button>
    </div>

    <div class="section-title">Browse by Area</div>
    <div class="areas">${areaChips}${state.areaFilter?`<button class="area-chip" onclick="setArea(null)">Clear</button>`:''}</div>

    <div class="section-title" id="listTitle">${listTitle}</div>
    <div class="filters-row">
      <select onchange="setTypeFilter(this.value)">
        <option value="">All types</option>
        ${[...new Set(PROPERTIES.map(p=>p.type))].map(t=>`<option ${state.typeFilter===t?'selected':''}>${t}</option>`).join('')}
      </select>
      <select onchange="setSort(this.value)">
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
      <button class="btn btn-primary" onclick="document.getElementById('grid').scrollIntoView({behavior:'smooth'})">Start a Verification</button>
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

export function setArea(a){ state.areaFilter=a; renderList(); document.querySelectorAll('.area-chip').forEach(c=>c.classList.remove('active')); if(a) event.target.classList.add('active'); }

function propCard(p){
  const ov = overallStatus(p);
  const vtext = ov==='verified'?'✓ Verification Available':(ov==='unchecked'?'Not Verified':'⚠ Review Required');
  return `<div class="pcard">
    <div class="thumb" onclick="nav('detail','${p.id}')" style="background-image:linear-gradient(0deg,rgba(0,0,0,.12),rgba(0,0,0,.02)),url('${p.image}');background-size:cover;background-position:center;">
      <button class="fav" onclick="event.stopPropagation();toggleSave('${p.id}')">${state.saved.has(p.id)?'♥':'♡'}</button>
      <span class="type-tag">${p.type}</span>
    </div>
    <div class="body">
      <div class="title">${p.title}</div>
      <div class="loc">${p.area}</div>
      <div class="price">${p.priceLabel}</div>
      <div class="size">${p.size}${p.beds?` · ${p.beds} Bed`:''}</div>
      <div class="vrow ${ov==='unchecked'?'mute':''}">${vtext}</div>
      <button class="viewbtn" onclick="nav('detail','${p.id}')">View Property</button>
    </div>
  </div>`;
}

export function toggleSave(id){ state.saved.has(id)?state.saved.delete(id):state.saved.add(id); renderList(); }

/* Filter inputs (replace former inline `state.x=this.value` handlers). */
export function setSearch(value){ state.search = value; renderList(); }
export function setTypeFilter(value){ state.typeFilter = value; renderList(); }
export function setSort(value){ state.sort = value; renderList(); }
