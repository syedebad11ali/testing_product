/* features/property.js — Property detail, per-property verification, report and the saved/verified/reports lists. */
import { LOGO_URL } from '../config.js';
import { CATS, CAT_ICONS, PROPERTIES, STATUS_META } from '../data/properties.js';
import { overallStatus } from '../domain/propertyStatus.js';
import { state } from '../state/store.js';

/* --- DETAIL --- */
export function renderDetail(id){
  const p = PROPERTIES.find(x=>x.id===id);
  const ov = overallStatus(p);
  return `
  <div class="hero" style="background-image:linear-gradient(180deg, rgba(15,42,61,.18), rgba(15,42,61,.34)), url('${p.image}'); background-size:cover; background-position:center; background-repeat:no-repeat;">
    <button class="backbtn" onclick="nav('home')">←</button>
    <button class="favbtn" onclick="toggleSave('${p.id}')">${state.saved.has(p.id)?'♥':'♡'}</button>
  </div>
  <div class="detail-card">
    <div class="d-title">${p.title}</div>
    <div class="d-loc">${p.area}, Karachi</div>
    <div class="d-price">${p.priceLabel}</div>
    <div class="d-stats">
      <div class="d-stat">📐 ${p.size}</div>
      ${p.beds?`<div class="d-stat">🛏 ${p.beds} Beds</div>`:''}
      ${p.baths?`<div class="d-stat">🛁 ${p.baths} Baths</div>`:''}
      <div class="d-stat" style="color:${ov==='verified'?'var(--ok)':ov==='issue'?'var(--bad)':ov==='review'?'var(--warn)':'var(--mute)'}">${STATUS_META[ov].icon} ${STATUS_META[ov].label}</div>
    </div>

    <div class="section-title" style="margin-top:20px;margin-bottom:8px;">Basic Information</div>
    <div class="info-grid">
      <div><span class="lbl">Property Type</span><span class="val">${p.type}</span></div>
      <div><span class="lbl">Reference</span><span class="val">${p.plot}</span></div>
      ${p.survey!=='—'?`<div><span class="lbl">Survey No.</span><span class="val">${p.survey}</span></div>`:''}
      ${p.deh!=='—'?`<div><span class="lbl">Deh</span><span class="val">${p.deh}</span></div>`:''}
      ${p.scheme!=='—'?`<div><span class="lbl">Scheme</span><span class="val">${p.scheme}</span></div>`:''}
    </div>

    <div class="owner-card">
      <div class="owner-avatar">${p.owner.split(' ').map(w=>w[0]).slice(0,2).join('')}</div>
      <div>
        <div class="owner-name">${p.owner}</div>
        <div class="owner-role">${p.ownerRole} · ${p.sellerType}</div>
      </div>
    </div>

    <details class="desc" open>
      <summary>Description &amp; Features ▾</summary>
      <p>${p.desc}</p>
    </details>

    <div class="action-row">
      <button class="btn btn-outline" onclick="toggleSave('${p.id}')">${state.saved.has(p.id)?'Saved':'Save Property'}</button>
      <button class="btn btn-outline" onclick="openChat()">Contact Seller</button>
      <button class="verify-cta-btn" onclick="nav('verify','${p.id}')">🛡 Verify This Property</button>
    </div>
  </div>
  <div style="height:24px;"></div>`;
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
          <div class="section-title" style="font-size:12.5px;margin:12px 0 0;">Enter property &amp; owner details</div>
          <label>Owner CNIC</label>
          <input id="cnic-${p.id}" placeholder="e.g. 42101-1234567-1">
          <label>Plot / Survey Number</label>
          <input id="plot-${p.id}" value="${p.plot!=='—'?p.plot:''}">
          <label>Owner Name</label>
          <input id="ownername-${p.id}" value="${p.owner}">
          <div class="save-row">
            <button class="vcat-btn" type="button" onclick="saveManualInfo('${p.id}')">Save Details</button>
            <span class="saved-msg" id="savedmsg-${p.id}">✓ Saved</span>
          </div>
        </div>
        <div class="upload-box">
          <div style="font-size:12px;color:var(--sub);margin-bottom:8px;">Not sure whether a document is genuine? Upload it here to check.</div>
          <label class="upload-btn" for="fileup-${p.id}">📎 Upload document to check</label>
          <input type="file" id="fileup-${p.id}" onchange="handleDocUpload(this,'${p.id}')">
          <div class="upload-filename" id="uf-${p.id}"></div>
          <div class="processing" id="proc-${p.id}"><span class="spin"></span> Extracting &amp; checking document…</div>
          <div class="auth-result" id="ar-${p.id}">
            <div class="arow"><span>Reference on file</span><span>${p.plot}</span></div>
            <div class="arow"><span>Reference match</span><span>${v.status==='issue'?'No':'Yes'}</span></div>
            <div class="arow"><span>Result</span><span class="status-badge ${m.color}">${m.icon} ${m.label}</span></div>
            <div class="auth-note">This is a document analysis, not an official government or bank authentication.</div>
          </div>
        </div>`;
    }
    return `<div class="vitem" id="vitem-${key}">
      <div class="vitem-row" onclick="document.getElementById('vitem-${key}').classList.toggle('open')">
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
  <div class="header" style="padding-bottom:20px;">
    <div class="header-top">
      <button class="icon-btn" onclick="nav('detail','${p.id}')"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m15 18-6-6 6-6"/></svg></button>
      <div class="logo-badge"><img src="${LOGO_URL}" alt="Karachi Property Trust"></div>
    </div>
    <div class="brand-block"><div class="brand" style="font-size:19px;">Property Verification</div><div class="tagline">Independent check, not a purchase transaction</div></div>
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
    <div class="progress-label" style="display:flex;justify-content:space-between;"><span>Verification Progress</span><span>${pct}% Checked</span></div>
    <div class="progress-track"><div class="progress-fill" style="width:${pct}%"></div></div>

    <div class="section-title" style="margin-top:20px;">Verification Categories</div>
    <div class="section-sub">Tap a category to see details, add information, or upload a document.</div>
    ${rows}

    <div class="section-title">Risk &amp; Trust Summary</div>
    <div class="stat-row">
      <div class="stat-box"><div class="stat-num" style="color:var(--ok)">${verifiedCount}</div><div class="stat-lbl">Verified</div></div>
      <div class="stat-box"><div class="stat-num" style="color:var(--warn)">${reviewCount}</div><div class="stat-lbl">Review Required</div></div>
      <div class="stat-box"><div class="stat-num" style="color:var(--mute)">${uncheckedCount}</div><div class="stat-lbl">Not Verified</div></div>
    </div>
    <div class="disclaimer" style="margin-top:12px;">This is a document and record analysis, not an official government or bank authentication. Treat "Review Required" items as things to double-check with the relevant authority before proceeding.</div>

    <button class="btn btn-primary btn-block" onclick="nav('report','${p.id}')">View Full Report</button>
  </main>`;
}

export function saveManualInfo(id){
  const msg = document.getElementById('savedmsg-'+id);
  if(!msg) return;
  msg.style.display='inline';
  clearTimeout(msg._t);
  msg._t = setTimeout(()=>{ msg.style.display='none'; }, 2200);
}

export function handleDocUpload(el,id){
  const file = el.files[0]; if(!file) return;
  document.getElementById('uf-'+id).textContent = 'File: '+file.name;
  const proc = document.getElementById('proc-'+id), ar = document.getElementById('ar-'+id);
  ar.classList.remove('show'); proc.classList.add('show');
  setTimeout(()=>{ proc.classList.remove('show'); ar.classList.add('show'); }, 1500);
}

/* --- REPORT --- */
export function renderReport(id){
  const p = PROPERTIES.find(x=>x.id===id);
  const ov = overallStatus(p);
  const today = new Date().toLocaleDateString('en-GB',{day:'numeric',month:'long',year:'numeric'});
  return `
  <div class="header" style="padding-bottom:20px;">
    <div class="header-top">
      <button class="icon-btn" onclick="nav('verify','${p.id}')"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m15 18-6-6 6-6"/></svg></button>
      <div class="logo-badge"><img src="${LOGO_URL}" alt="Karachi Property Trust"></div>
    </div>
    <div class="brand-block"><div class="brand" style="font-size:19px;">Verification Report</div><div class="tagline">Generated ${today}</div></div>
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
      <span class="status-badge ${STATUS_META[ov].color}" style="font-size:13px;padding:7px 14px;">${STATUS_META[ov].icon} ${STATUS_META[ov].label}</span>
      <div class="disclaimer">This report reflects document analysis and available records only. It is not an official land-registry, bank, or court authentication. Outstanding checks should be confirmed with the relevant authority before finalising any transaction.</div>
    </div>
    <div class="action-row" style="grid-template-columns:1fr 1fr 1fr;">
      <button class="btn btn-outline" onclick="window.print()">Download</button>
      <button class="btn btn-outline" onclick="openChat()">Share</button>
      <button class="btn btn-primary" onclick="nav('detail','${p.id}')">Done</button>
    </div>
  </main>`;
}

/* --- SUB LISTS: My Verifications / Saved / Reports --- */
export function renderSubList(kind){
  const cfg = {
    verifications:{title:'My Verifications', list:PROPERTIES, empty:'', actionLabel:'Continue Verification', actionFn:p=>`nav('verify','${p.id}')`},
    saved:{title:'Saved Properties', list:PROPERTIES.filter(p=>state.saved.has(p.id)), empty:'You haven\u2019t saved any properties yet. Tap the heart icon on a listing to save it here.', actionLabel:'View Property', actionFn:p=>`nav('detail','${p.id}')`},
    reports:{title:'Report A Scam', list:PROPERTIES, empty:'', actionLabel:'View Report', actionFn:p=>`nav('report','${p.id}')`}
  }[kind];

  const rows = cfg.list.map(p=>{
    const m = STATUS_META[overallStatus(p)];
    const verifiedImage = p.VerifiedImage || p.VerificationImage;
    return `<div class="vprop" style="margin-bottom:10px;">
      <div class="thumb" onclick="nav('detail','${p.id}')" style="cursor:pointer;background-image:url('${verifiedImage}');background-size:cover;background-position:center;"></div>
      <div style="flex:1;min-width:0;">
        <div class="t">${p.title}</div>
        <div class="l">Property ID: ${p.id}</div>
        <div class="l">${p.area}</div>
        <span class="status-badge ${m.color}" style="margin-top:6px;">${m.icon} ${m.label}</span>
      </div>
      <button class="btn btn-outline" style="padding:8px 12px;font-size:11px;flex-shrink:0;" onclick="${cfg.actionFn(p)}">${cfg.actionLabel}</button>
    </div>`;
  }).join('') || `<div class="empty">${cfg.empty}</div>`;

  const reportOptions = kind === 'reports' ? `
    <div class="doc-options" style="margin-bottom:18px;">
      <div class="doc-option-card" onclick="openReportEvidenceUpload()">
        <div class="doc-option-icon">📄</div>
        <h3>Upload Evidence</h3>
        <p>Choose a document or image from your device to report a suspected scam.</p>
        <button class="btn btn-primary btn-block" style="margin-top:0;" onclick="event.stopPropagation();openReportEvidenceUpload()">Upload Evidence</button>
      </div>
      <div class="doc-option-card" onclick="openReportEvidenceCamera()">
        <div class="doc-option-icon">📷</div>
        <h3>Scan / Capture Evidence</h3>
        <p>Use your camera to capture a clear image of the property or document.</p>
        <button class="btn btn-primary btn-block" style="margin-top:0;" onclick="event.stopPropagation();openReportEvidenceCamera()">Open Camera</button>
      </div>
    </div>` : '';

  const headerSubtitle = kind === 'reports'
    ? `<div class="tagline" style="margin-top:8px; max-width:960px; line-height:1.4; opacity:0.92;">See a scam? Snap it, report it, stop it. Expose the fake and protect your neighborhood.</div>`
    : '';

  return `
  <div class="header" style="padding-bottom:20px;">
    <div class="header-top">
      <button class="icon-btn" onclick="nav('home')"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m15 18-6-6 6-6"/></svg></button>
      <div class="logo-badge"><img src="${LOGO_URL}" alt="Karachi Property Trust"></div>
    </div>
    <div class="brand-block"><div class="brand" style="font-size:19px;">${cfg.title}</div>${headerSubtitle}</div>
  </div>
  <main>${kind==='reports'?reportOptions:''}${kind==='verifications'?'<div class="section-title">VERIFIED PROPERTY</div>':''}${rows}</main>`;
}
