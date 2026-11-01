/* features/property.js — Property detail, per-property verification, report and the saved/verified/reports lists. */
import { LOGO_URL } from '../config.js';
import { CATS, CAT_ICONS, DEMO_PROPERTY_DISPLAY_STATUS, PROPERTIES, STATUS_META } from '../data/properties.js';
import { overallStatus } from '../domain/propertyStatus.js';
import { favoritesRuntime, state } from '../state/store.js';
import { isAccountSession } from '../services/sessionUser.js';
import { showLoginRequired } from './loginPrompt.js';

/* --- DETAIL --- */
/** The owner card. Only a LOADED registered user or admin (`canSeeOwner === true`) sees the owner; anything else (guest, signed out, session still
 *  loading, failed lookup, any non-true value) gets a neutral card with no name, initials or role (fail closed). Display-only: the demo records
 *  are synthetic and `properties.js` is still a public file. */
export function ownerCardHtml(p, canSeeOwner){
  if(canSeeOwner === true) return `<div class="owner-card">
      <div class="owner-avatar">${p.owner.split(' ').map(w=>w[0]).slice(0,2).join('')}</div>
      <div>
        <div class="owner-name">${p.owner}</div>
        <div class="owner-role">${p.ownerRole} · ${p.sellerType}</div>
      </div>
    </div>`;
  return `<div class="owner-card" data-owner-hidden>
      <div>
        <div class="owner-name">Listed by ${p.sellerType}</div>
        <div class="owner-role">Log in or sign up to see the owner details.</div>
        <button type="button" class="btn btn-outline" data-onclick="showOwnerLogin()">Log in / Sign up</button>
      </div>
    </div>`;
}
/** The neutral card's button: the shared "Login required" dialog, no navigation, no request. */
export function showOwnerLogin(){ showLoginRequired({ feature: 'Owner details' }); }

export function renderDetail(id){
  const p = PROPERTIES.find(x=>x.id===id);
  const ov = DEMO_PROPERTY_DISPLAY_STATUS;
  return `
  <div class="hero bg-photo bg-grad-hero" data-bg="${p.image}">
    <button class="backbtn" data-onclick="nav('home')">←</button>
    <button class="favbtn${state.saved.has(p.id)?' saved':''}" data-favorite-id="${p.id}" aria-pressed="${state.saved.has(p.id)}" aria-label="${state.saved.has(p.id)?'Remove from saved properties':'Save property'}" data-onclick="toggleSave('${p.id}')"><span class="favorite-heart" data-favorite-heart aria-hidden="true">${state.saved.has(p.id)?'♥':'♡'}</span></button>
  </div>
  <div class="detail-card">
    <div class="d-title" role="heading" aria-level="1">${p.title}</div>
    <div class="d-loc">${p.area}, Karachi</div>
    <div class="d-price">${p.priceLabel}</div>
    <div class="d-stats">
      <div class="d-stat">📐 ${p.size}</div>
      ${p.beds?`<div class="d-stat">🛏 ${p.beds} Beds</div>`:''}
      ${p.baths?`<div class="d-stat">🛁 ${p.baths} Baths</div>`:''}
      <div class="d-stat ${ov==='verified'?'tone-ok':ov==='issue'?'tone-bad':ov==='review'?'tone-warn':'tone-mute'}">${STATUS_META[ov].icon} ${STATUS_META[ov].label}</div>
    </div>

    <div class="section-title u-margin-top-20px-margin-bottom-8px">Basic Information</div>
    <div class="info-grid">
      <div><span class="lbl">Property Type</span><span class="val">${p.type}</span></div>
      <div><span class="lbl">Reference</span><span class="val">${p.plot}</span></div>
      ${p.survey!=='—'?`<div><span class="lbl">Survey No.</span><span class="val">${p.survey}</span></div>`:''}
      ${p.deh!=='—'?`<div><span class="lbl">Deh</span><span class="val">${p.deh}</span></div>`:''}
      ${p.scheme!=='—'?`<div><span class="lbl">Scheme</span><span class="val">${p.scheme}</span></div>`:''}
    </div>

    ${ownerCardHtml(p, isAccountSession())}

    <details class="desc" open>
      <summary>Description &amp; Features ▾</summary>
      <p>${p.desc}</p>
    </details>

    <div class="action-row">
      <button class="btn btn-outline" data-favorite-id="${p.id}" data-favorite-label aria-pressed="${state.saved.has(p.id)}" data-onclick="toggleSave('${p.id}')"><span data-favorite-label>${state.saved.has(p.id)?'Saved':'Save Property'}</span></button>
      <button class="btn btn-outline" data-onclick="openChat()">Contact Seller</button>
      <button class="btn btn-primary" data-onclick="chatWithSeller('${p.id}')">Chat with seller</button>
      <button class="verify-cta-btn" data-onclick="nav('verify','${p.id}')">🛡 Verify This Property</button>
    </div>
    <p class="seller-chat-note" id="sellerChatNote" role="status" aria-live="polite"></p>
  </div>
  <div class="u-height-24px"></div>`;
}

export function renderVerify(id){
  const p = PROPERTIES.find(x=>x.id===id);
  const checkedCount = CATS.filter(c=>p.verification[c[0]].status!=='unchecked').length;
  const verifiedCount = CATS.filter(c=>p.verification[c[0]].status==='verified').length;
  const reviewCount = CATS.filter(c=>['review','issue'].includes(p.verification[c[0]].status)).length;
  const uncheckedCount = CATS.length-checkedCount;
  const pct = Math.round(checkedCount/CATS.length*100);

  const rows = CATS.map(([key,label])=>{
    const v = p.verification[key];
    const m = STATUS_META[v.status];
    let panel = `<div class="vcat-note">${v.note}</div>`;
    if(key==='documents'){
      panel += `
        <div class="mini-form">
          <div class="section-title u-font-size-12-5px-margin-12px-0-0">Enter property &amp; owner details</div>
          <label for="cnic-${p.id}">Owner CNIC</label>
          <input id="cnic-${p.id}" placeholder="e.g. 00000-0000000-0">
          <label for="plot-${p.id}">Plot / Survey Number</label>
          <input id="plot-${p.id}" value="${p.plot!=='—'?p.plot:''}">
          <label for="ownername-${p.id}">Owner Name</label>
          <input id="ownername-${p.id}" value="${p.owner}">
          <div class="save-row">
            <button class="vcat-btn" type="button" data-onclick="saveManualInfo('${p.id}')">Save Details</button>
            <span class="saved-msg" id="savedmsg-${p.id}">✓ Saved</span>
          </div>
        </div>
        <div class="upload-box" id="docnotice-${p.id}">
          <div class="u-font-size-12px-color-var-sub-margin-bo-2da11">Checking an uploaded document against this specific property is not available on this page, and no file is read or checked here.</div>
          <div class="auth-note">To check a document, use the document check. It compares the document with the records available in this app. Its result is indicative only and is not official ownership authentication.</div>
          <button class="vcat-btn" type="button" data-onclick="openVerifyDocument()">Open document check</button>
        </div>`;
    }
    return `<div class="vitem" id="vitem-${key}">
      <div class="vitem-row" data-onclick="toggleOpen('vitem-${key}')">
        <div class="vitem-icon">${CAT_ICONS[key]}</div>
        <div class="vitem-main">
          <div class="vitem-title">${label}</div>
          <div class="vitem-status ${v.status}">${m.label}</div>
        </div>
        <span class="vitem-chev">›</span>
      </div>
      <div class="vitem-panel">${panel}</div>
    </div>`;
  }).join('');

  return `
  <div class="header u-padding-bottom-20px">
    <div class="header-top">
      <button class="icon-btn" data-onclick="nav('detail','${p.id}')" aria-label="Back"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m15 18-6-6 6-6"/></svg></button>
      <div class="logo-badge"><img src="${LOGO_URL}" alt="Karachi Property Trust"></div>
    </div>
    <div class="brand-block"><div class="brand u-font-size-19px" role="heading" aria-level="1">Property Verification</div><div class="tagline">Independent check, not a purchase transaction</div></div>
  </div>
  <main>
    <div class="vprop">
      <div class="thumb"></div>
      <div>
        <div class="t">${p.title}</div>
        <div class="l">${p.area} · ${p.plot}</div>
        <div class="l">Owner: ${p.owner}</div>
      </div>
    </div>
    <div class="progress-label u-display-flex-justify-content-space-between"><span>Verification Progress</span><span>${pct}% Checked</span></div>
    <div class="progress-track"><div class="progress-fill" data-w="${pct}"></div></div>

    <div class="section-title u-margin-top-20px">Verification Categories</div>
    <div class="section-sub">Tap a category to see details, add information, or upload a document.</div>
    ${rows}

    <div class="section-title">Risk &amp; Trust Summary</div>
    <div class="stat-row">
      <div class="stat-box"><div class="stat-num u-color-var-ok">${verifiedCount}</div><div class="stat-lbl">Verified</div></div>
      <div class="stat-box"><div class="stat-num u-color-var-warn">${reviewCount}</div><div class="stat-lbl">Review Required</div></div>
      <div class="stat-box"><div class="stat-num u-color-var-mute">${uncheckedCount}</div><div class="stat-lbl">Not Verified</div></div>
    </div>
    <div class="disclaimer u-margin-top-12px">This is a document and record analysis, not an official government or bank authentication. Treat "Review Required" items as things to double-check with the relevant authority before proceeding.</div>

    <button class="btn btn-primary btn-block" data-onclick="nav('report','${p.id}')">View Full Report</button>
  </main>`;
}

export function saveManualInfo(id){
  const msg = document.getElementById('savedmsg-'+id);
  if(!msg) return;
  msg.style.display='inline';
  clearTimeout(msg._t);
  msg._t = setTimeout(()=>{ msg.style.display='none'; }, 2200);
}

/* --- REPORT --- */
export function renderReport(id){
  const p = PROPERTIES.find(x=>x.id===id);
  const ov = DEMO_PROPERTY_DISPLAY_STATUS;
  const today = new Date().toLocaleDateString('en-GB',{day:'numeric',month:'long',year:'numeric'});
  return `
  <div class="header u-padding-bottom-20px">
    <div class="header-top">
      <button class="icon-btn" data-onclick="nav('verify','${p.id}')" aria-label="Back"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m15 18-6-6 6-6"/></svg></button>
      <div class="logo-badge"><img src="${LOGO_URL}" alt="Karachi Property Trust"></div>
    </div>
    <div class="brand-block"><div class="brand u-font-size-19px">Verification Report</div><div class="tagline">Generated ${today}</div></div>
  </div>
  <main>
    <div class="report-block">
      <h4>Property</h4>
      <div class="report-row"><span>Title</span><span>${p.title}</span></div>
      <div class="report-row"><span>Location</span><span>${p.area}</span></div>
      <div class="report-row"><span>Reference</span><span>${p.plot}</span></div>
      <div class="report-row"><span>Price</span><span>${p.priceLabel}</span></div>
      <div class="report-row"><span>Owner</span><span>${p.owner}</span></div>
    </div>
    <div class="report-block">
      <h4>Category Results</h4>
      ${CATS.map(([key,label])=>{const m=STATUS_META[p.verification[key].status];return `<div class="report-row"><span>${label}</span><span class="status-badge ${m.color}">${m.icon} ${m.label}</span></div>`}).join('')}
    </div>
    <div class="report-block">
      <h4>Overall Result</h4>
      <span class="status-badge ${STATUS_META[ov].color} u-font-size-13px-padding-7px-14px">${STATUS_META[ov].icon} ${STATUS_META[ov].label}</span>
      <div class="disclaimer">This report reflects document analysis and available records only. It is not an official land-registry, bank, or court authentication. Outstanding checks should be confirmed with the relevant authority before finalising any transaction.</div>
    </div>
    <div class="action-row u-grid-template-columns-1fr-1fr-1fr">
      <button class="btn btn-outline" data-onclick="print()">Download</button>
      <button class="btn btn-outline" data-onclick="openChat()">Share</button>
      <button class="btn btn-primary" data-onclick="nav('detail','${p.id}')">Done</button>
    </div>
  </main>`;
}

/* --- SUB LISTS: My Verifications / Saved / Reports --- */
/** G5.2: an empty saved list is only "you have none" once the account's list really loaded; otherwise say so instead of showing a false empty result. */
function savedListEmptyText(){
  if(favoritesRuntime.status==='ready') return 'You haven\u2019t saved any properties yet. Tap the heart icon on a listing to save it here.';
  if(favoritesRuntime.status==='error') return 'We could not load your saved properties. Please try again.';
  return 'Loading your saved properties\u2026';
}
export function renderSubList(kind){
  const cfg = {
    verifications:{title:'My Verifications', list:PROPERTIES, empty:'', actionLabel:'Continue Verification', actionFn:p=>`nav('verify','${p.id}')`},
    saved:{title:'Saved Properties', list:PROPERTIES.filter(p=>state.saved.has(p.id)), empty:savedListEmptyText(), actionLabel:'View Property', actionFn:p=>`nav('detail','${p.id}')`},
    reports:{title:'Report A Scam', list:PROPERTIES, empty:'', actionLabel:'View Report', actionFn:p=>`nav('report','${p.id}')`}
  }[kind];

  const rows = cfg.list.map(p=>{
    const status = kind === 'reports' ? overallStatus(p) : DEMO_PROPERTY_DISPLAY_STATUS;
    const m = STATUS_META[status];
    const verifiedImage = p.VerifiedImage || p.VerificationImage;
    return `<div class="vprop u-margin-bottom-10px">
      <div class="thumb bg-photo u-cursor-pointer" data-onclick="nav('detail','${p.id}')" data-bg="${verifiedImage}"></div>
      <div class="u-flex-1-min-width-0">
        <div class="t">${p.title}</div>
        <div class="l">Property ID: ${p.id}</div>
        <div class="l">${p.area}</div>
        <span class="status-badge ${m.color} u-margin-top-6px">${m.icon} ${m.label}</span>
      </div>
      <button class="btn btn-outline u-padding-8px-12px-font-size-11px-flex-s-ff380" data-onclick="${cfg.actionFn(p)}">${cfg.actionLabel}</button>
    </div>`;
  }).join('') || `<div class="empty">${cfg.empty}</div>`;

  const reportOptions = kind === 'reports' ? `
    <div class="doc-options u-margin-bottom-18px">
      <div class="doc-option-card" data-onclick="openReportEvidenceUpload()">
        <div class="doc-option-icon">📄</div>
        <h3>Upload Evidence</h3>
        <p>Choose a document or image from your device to report a suspected scam.</p>
        <button class="btn btn-primary btn-block u-margin-top-0" data-onclick="stopPropagation();openReportEvidenceUpload()">Upload Evidence</button>
      </div>
      <div class="doc-option-card" data-onclick="openReportEvidenceCamera()">
        <div class="doc-option-icon">📷</div>
        <h3>Scan / Capture Evidence</h3>
        <p>Use your camera to capture a clear image of the property or document.</p>
        <button class="btn btn-primary btn-block u-margin-top-0" data-onclick="stopPropagation();openReportEvidenceCamera()">Open Camera</button>
      </div>
    </div>` : '';

  const headerSubtitle = kind === 'reports'
    ? `<div class="tagline u-margin-top-8px-max-width-960px-line-he-c68b2">See a scam? Snap it, report it, stop it. Expose the fake and protect your neighborhood.</div>`
    : '';

  return `
  <div class="header u-padding-bottom-20px">
    <div class="header-top">
      <button class="icon-btn" data-onclick="nav('home')"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m15 18-6-6 6-6"/></svg></button>
      <div class="logo-badge"><img src="${LOGO_URL}" alt="Karachi Property Trust"></div>
    </div>
    <div class="brand-block"><div class="brand u-font-size-19px">${cfg.title}</div>${headerSubtitle}</div>
  </div>
  <main>${kind==='reports'?reportOptions:''}${kind==='verifications'?'<div class="section-title">VERIFIED PROPERTY</div>':''}${rows}</main>`;
}
