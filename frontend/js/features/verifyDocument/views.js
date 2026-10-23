/* features/verifyDocument/views.js — 'Verify Your Document' screens (landing, type select, upload, analysis, result, history). */
import { render } from '../../app/router.js';
import { LOGO_URL } from '../../config.js';
import { escapeHtml } from '../../core/html.js';
import { AUTO_DOC_TYPES, AUTO_STATUS_META, DOC_FIELD_DEFS, DOC_STATUS_META, DOC_TYPES, DOC_TYPE_FIELDS, SAMPLE_DOCS } from '../../data/documentTypes.js';
import { PROPERTIES } from '../../data/properties.js';
import { allVerificationRecords, maskCnic } from '../../domain/documentVerification.js';
import { renderDocCamera } from './camera.js';
import { docHistory, docState } from '../../state/store.js';

export function renderOcrProgressOnly(){
  const bar = document.getElementById('ocrProgressBar');
  const label = document.getElementById('ocrPhaseLabel');
  if(bar && label){ bar.style.width = (docState.ocrProgress||0)+'%'; label.textContent = docState.ocrPhaseLabel||''; }
  else render();
}

export function renderVerifyDocument(){
  switch(docState.step){
    case 'autotype': return renderDocAutoTypeSelect();
    case 'type': return renderDocTypeSelect();
    case 'upload': return renderDocUploadForm();
    case 'camera': return renderDocCamera();
    case 'ocr-analyzing': return renderOcrAnalyzing();
    case 'manual': return renderDocManualForm();
    case 'manual-analyzing': return renderDocAnalyzing('Checking Details');
    case 'result':
      if(docState.result && docState.result.pipeline==='auto'){
        return docState.result.status==='ocr_failed' ? renderDocOcrFailedScreen(docState.result) : renderAutoDocResult(docState.result);
      }
      return renderDocResult();
    case 'manual-result': return renderDocResult();
    case 'history': return renderDocHistoryList();
    default: return renderDocLanding();
  }
}

function renderDocLanding(){
  return `
  ${docHeader('Verify Your Document','Upload or capture a clear photo of your property document. It will be read automatically.', "nav('home')")}
  <main>
    <div class="doc-options">
      <div class="doc-option-card" onclick="docPickMethod('upload')">
        <div class="doc-option-icon">📄</div>
        <h3>Upload Document</h3>
        <p>Choose a document from your device. We'll nead it automatically — no typing required.</p>
        <button class="btn btn-primary btn-block" style="margin-top:0;" onclick="event.stopPropagation();docPickMethod('upload')">Upload Document</button>
      </div>
      <div class="doc-option-card" onclick="docPickMethod('camera')">
        <div class="doc-option-icon">📷</div>
        <h3>Scan / Capture Document</h3>
        <p>Use your camera to capture a clear image of your document.</p>
        <button class="btn btn-primary btn-block" style="margin-top:0;" onclick="event.stopPropagation();docPickMethod('camera')">Open Camera</button>
      </div>
    </div>

    <div class="auth-note" style="text-align:center;margin-top:6px;">
      Can't provide a readable document?
      <a href="javascript:void(0)" onclick="docPickMethod('manual')">Enter details manually instead</a>.
    </div>

    ${renderSampleDocsSection()}

    <div class="section-title">Not the Same as "Verify This Property"</div>
    <div class="vcat-note" style="padding:0 2px;">"Verify This Property" checks an entire property listing across multiple categories. "Verify Your Document" independently checks one document — even if the property isn't listed here at all.</div>

    ${docHistory.length ? `
    <div class="section-title">My Document Checks</div>
    <div class="vcat" style="cursor:pointer;" onclick="docGoStep('history')">
      <div class="vcat-head"><div class="vcat-title">📁 View past document checks</div><span class="vitem-chev">›</span></div>
      <div class="vcat-note">${docHistory.length} result${docHistory.length===1?'':'s'} saved on this device.</div>
    </div>` : ''}
  </main>`;
}

function renderDocTypeSelect(){
  return `
  ${docHeader('Select Document Type', docState.method==='upload'?'What kind of document are you uploading?':docState.method==='camera'?'What kind of document are you capturing?':'What kind of document is this?', "docGoStep('landing')")}
  <main>
    <div class="doctype-grid">
      ${DOC_TYPES.map(t=>`<button class="doctype-chip" onclick="docPickType(${JSON.stringify(t)})">${t}</button>`).join('')}
    </div>
  </main>`;
}

function renderDocAutoTypeSelect(){
  return `
  ${docHeader('Select Document Type','Choose the kind of document. You will not need to type any details — they are read automatically.', "docGoStep('landing')")}
  <main><div class="doctype-grid">
    ${AUTO_DOC_TYPES.map(t=>`<button class="doctype-chip" onclick="docPickAutoType('${t[0]}')">${t[1]}</button>`).join('')}
  </div></main>`;
}

function renderSampleDocsSection(){
  return `
  <div class="section-title">Try Sample Documents <span style="font-size:10px;font-weight:600;color:var(--mute);">(demo/testing only — fictional)</span></div>
  <div class="vcat">${SAMPLE_DOCS.map(d=>`
    <div class="check-item" style="align-items:center;gap:6px;flex-wrap:wrap;">
      <span style="min-width:130px;font-weight:700;">${d[1]}</span>
      <button class="btn btn-outline" style="padding:4px 8px;font-size:11px;margin:0;" onclick="docStartSample('${d[0]}','${d[2]}','matching','png')">Matching</button>
      <button class="btn btn-outline" style="padding:4px 8px;font-size:11px;margin:0;" onclick="docStartSample('${d[0]}','${d[2]}','mismatch','png')">Mismatch</button>
      <button class="btn btn-outline" style="padding:4px 8px;font-size:11px;margin:0;" onclick="docStartSample('${d[0]}','${d[2]}','matching','pdf')">PDF</button>
    </div>`).join('')}</div>`;
}

function docHeader(title, subtitle, backAction){
  return `<div class="header" style="padding-bottom:20px;">
    <div class="header-top">
      <button class="icon-btn" onclick="${backAction}" aria-label="Back"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m15 18-6-6 6-6"/></svg></button>
      <div class="logo-badge"><img src="${LOGO_URL}" alt="Karachi Property Trust"></div>
    </div>
    <div class="brand-block"><div class="brand" style="font-size:19px;">${title}</div>${subtitle?`<div class="tagline">${subtitle}</div>`:''}</div>
  </div>`;
}

function docFieldsFormHtml(fieldsForType){
  return `<div class="mini-form">
    ${fieldsForType.map(k=>{
      const def = DOC_FIELD_DEFS[k]; const val = docState.fields[k]||'';
      if(def.type==='textarea') return `<label>${def.label}</label><textarea oninput="docSetField('${k}',this.value)">${val}</textarea>`;
      return `<label>${def.label}</label><input type="${def.type||'text'}" placeholder="${def.ph||'Not detected — please confirm'}" value="${val}" oninput="docSetField('${k}',this.value)">`;
    }).join('')}
  </div>`;
}

function renderDocUploadForm(){
  const f = docState.file;
  return `
  ${docHeader('Upload Document','Upload a clear photo of your property document. It will be read automatically.', "docGoStep('landing')")}
  <main>
    ${!f ? `
    <div class="dropzone">
      <div style="font-size:30px;">📎</div>
      <div style="font-weight:700;margin-top:8px;">Upload Your Property Document</div>
      <div style="font-size:12px;color:var(--sub);margin-top:4px;">JPG and PNG are read automatically. PDF is accepted but not yet auto-read in this build — a photo of the page works best.</div>
      <div class="dropzone-actions">
        <label class="upload-btn" for="docfile">Upload from Device</label>
        <input type="file" id="docfile" accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/*" onchange="docHandleFile(this)">
        <label class="upload-btn cam" for="docfilecam">📷 Take Photo</label>
        <input type="file" id="docfilecam" accept="image/*" capture="environment" onchange="docHandleFile(this)">
      </div>
      ${docState.fileError?`<div class="auth-note" style="color:var(--bad);margin-top:10px;">${escapeHtml(docState.fileError)}</div>`:''}
    </div>
    <div class="auth-note" style="text-align:center;margin-top:14px;">Can't provide a readable document? <a href="javascript:void(0)" onclick="docPickMethod('manual')">Enter details manually instead</a>.</div>
    ` : `
    <div class="file-chip">
      <div style="font-size:22px;">${f.type==='application/pdf'?'📄':'🖼️'}</div>
      <div class="fi"><div class="fn">${escapeHtml(f.name)}</div><div class="fs">${(f.size/1024/1024).toFixed(2)} MB</div></div>
      <button onclick="docRemoveFile()">Remove</button>
    </div>
    ${f.dataUrl ? `<img class="doc-preview-img" src="${f.dataUrl}" alt="Document preview">` : ''}
    <div class="auth-note" style="margin-top:10px;">Preparing to read this document…</div>
    `}
  </main>`;
}

function renderOcrAnalyzing(){
  return `
  ${docHeader('Reading Your Document','Please wait while we read and extract the information — this is the real OCR engine running in your browser.', "docGoStep('landing')")}
  <main>
    <div class="ocr-progress-wrap">
      <div class="ocr-progress-label" id="ocrPhaseLabel">${escapeHtml(docState.ocrPhaseLabel||'Reading document…')}</div>
      <div class="ocr-progress-track"><div class="ocr-progress-bar" id="ocrProgressBar" style="width:${docState.ocrProgress||0}%;"></div></div>
      <div class="auth-note" style="margin-top:14px;text-align:center;">Larger or lower-quality images can take longer to read.</div>
    </div>
  </main>`;
}

function renderDocOcrFailedScreen(r){
  return `
  ${docHeader('Unable to Read Document','', "openVerifyDocument()")}
  <main>
    <div class="assess-banner assess-mute">
      <div class="assess-icon" style="color:var(--mute)">–</div>
      <div class="assess-title">UNABLE TO VERIFY</div>
      <div class="assess-sub">${escapeHtml(r.message||'We could not extract enough readable information from this document.')}</div>
    </div>
    <div class="doc-options" style="margin-top:18px;grid-template-columns:1fr;gap:10px;">
      <button class="btn btn-primary btn-block" onclick="docPickMethod('camera')">Retake Photo</button>
      <button class="btn btn-outline btn-block" onclick="docPickMethod('upload')">Upload Another Image</button>
    </div>
    <div class="auth-note" style="margin-top:14px;text-align:center;">Can't provide a readable document? <a href="javascript:void(0)" onclick="docPickMethod('manual')">Enter details manually instead</a>.</div>
  </main>`;
}

function autoFieldRow(label, field){
  if(!field) return `<div class="check-item"><span class="mark" style="color:var(--mute)">–</span><span>${label}: not checked</span></div>`;
  if(field.conflict) return `<div class="check-item"><span class="mark" style="color:var(--bad)">⚠</span><span>${label}: conflicting values found — ${field.values.map(escapeHtml).join(' vs ')}</span></div>`;
  if(field.found){
    const shown = label==='CNIC' ? maskCnic(field.value) : field.display;
    return `<div class="check-item"><span class="mark" style="color:var(--ok)">✓</span><span>${label}: ${escapeHtml(shown)} <em style="opacity:.65;">(automatically extracted)</em></span></div>`;
  }
  return `<div class="check-item"><span class="mark" style="color:var(--warn);">⚠</span><span>${label}: not detected</span></div>`;
}

function renderAutoDocResult(r){
  const meta = AUTO_STATUS_META[r.status] || AUTO_STATUS_META.unable_to_verify;
  const matchedProperty = r.matchedPropertyId ? allVerificationRecords().find(p=>p.id===r.matchedPropertyId) : null;
  const isDemoRec = matchedProperty && !PROPERTIES.some(p=>p.id===matchedProperty.id);
  const ext = r.extraction || {};
  const pf = (ext.profile && ext.profile.fields) || ['name','cnic','plot'];
  return `
  ${docHeader('Document Result', ext.documentType ? ext.documentType.type : '', docState.historyIndex!=null ? "docGoStep('history')" : "openVerifyDocument()")}
  <main>
    <div class="section-title">Automatically Extracted Information</div>
    <div class="vcat">
      ${pf.includes('name')?autoFieldRow('Name', ext.ownerName):''}
      ${pf.includes('plot')?autoFieldRow('Plot Number', ext.plotNumber):''}
      ${pf.includes('cnic')?autoFieldRow('CNIC', ext.cnic):''}
      ${pf.includes('survey')?autoFieldRow('Survey Number', ext.surveyNumber):''}
      ${pf.includes('address')?autoFieldRow('Address', ext.address):''}
      ${pf.includes('approvedArea')?autoFieldRow('Approved Area', ext.approvedArea):''}
      ${pf.includes('paymentStatus')?autoFieldRow('Payment Status', ext.paymentStatus):''}
    </div>

    <div class="assess-banner assess-${meta.tone}">
      <div class="assess-icon" style="color:var(--${meta.tone})">${meta.icon}</div>
      <div class="assess-title">${meta.label}</div>
      ${r.reasons && r.reasons.length ? `<div class="assess-sub">${escapeHtml(r.reasons[0])}</div>` : `<div class="assess-sub">Assessment based on available checks</div>`}
    </div>

    ${r.reasons && r.reasons.length ? `<div class="section-title">Issues Found</div>
    <div class="vcat">${r.reasons.map(x=>`<div class="check-item"><span class="mark" style="color:var(--warn);">⚠</span><span>${escapeHtml(x)}</span></div>`).join('')}</div>` : ''}

    <div class="section-title">Checks Performed</div>
    <div class="vcat">${r.checks.map(c=>`<div class="check-item"><span class="mark" style="color:${c.ok===true?'var(--ok)':c.ok===false?'var(--bad)':'var(--mute)'}">${c.ok===true?'✓':c.ok===false?'⚠':'–'}</span><span>${escapeHtml(c.text)}</span></div>`).join('')}</div>

    ${matchedProperty ? `
    <div class="section-title">Possible Matching Property</div>
    <div class="vprop" ${isDemoRec?'':`style="cursor:pointer;" onclick="nav('detail','${matchedProperty.id}')"`}>
      <div class="thumb"></div>
      <div>
        <div class="t">${escapeHtml(matchedProperty.title)}</div>
        <div class="l">${escapeHtml(matchedProperty.area)} · ${escapeHtml(matchedProperty.plot)}</div>
        <div class="l">Owner on record: ${escapeHtml(matchedProperty.owner)}</div>
      </div>
    </div>
    ${isDemoRec?'<div class="auth-note">This is a fictional demo record used for testing.</div>':`<div class="doc-options" style="margin-top:10px;grid-template-columns:1fr 1fr;gap:10px;">
      <button class="btn btn-outline btn-block" style="margin-top:0;" onclick="nav('detail','${matchedProperty.id}')">View Property</button>
      <button class="btn btn-primary btn-block" style="margin-top:0;" onclick="nav('verify','${matchedProperty.id}')">Verify This Property</button>
    </div>`}` : ''}

    <div class="section-title">Limitations</div>
    <div class="vcat">${(r.limitations||[]).map(x=>`<div class="check-item"><span class="mark" style="color:var(--mute)">–</span><span>${escapeHtml(x)}</span></div>`).join('')}</div>

    <button class="btn btn-outline btn-block" style="margin-top:16px;" onclick="openVerifyDocument()">Check Another Document</button>
  </main>
  ${docState.showNotVerifiedModal ? renderNotVerifiedModal(r, meta) : ''}
  `;
}

function renderNotVerifiedModal(r, meta){
  return `
  <div class="modal-overlay" onclick="closeNotVerifiedModal(event)">
    <div class="modal-card" onclick="event.stopPropagation()">
      <div class="modal-icon" style="color:var(--bad)">${meta.icon}</div>
      <div class="modal-title">${meta.label}</div>
      <div class="modal-body">${(r.reasons && r.reasons.length) ? r.reasons.map(x=>`<p>${escapeHtml(x)}</p>`).join('') : '<p>We could not verify this document using the available information.</p>'}</div>
      <div class="modal-actions">
        <button class="btn btn-outline" onclick="docPickMethod('upload')">Try Another Document</button>
        <button class="btn btn-outline" onclick="closeNotVerifiedModal()">View Details</button>
        <button class="btn btn-primary" onclick="closeNotVerifiedModal()">Close</button>
      </div>
    </div>
  </div>`;
}

export function closeNotVerifiedModal(e){ if(e) e.stopPropagation(); docState.showNotVerifiedModal=false; render(); }

function renderDocManualForm(){
  const fieldsForType = DOC_TYPE_FIELDS[docState.docType] || DOC_TYPE_FIELDS['Other / Unknown Document'];
  return `
  ${docHeader('Enter Details Manually', docState.docType, "docGoStep('type')")}
  <main>
    <div class="disclaimer">No document file will be analyzed here. This method can check the entered information for completeness, internal consistency, and matches against available property records — it cannot inspect the document's visual or file characteristics.</div>
    <div class="section-title">Document Information</div>
    ${docFieldsFormHtml(fieldsForType)}
    ${docState.formError?`<div class="auth-note" style="color:var(--bad);">${docState.formError}</div>`:''}
    <button class="btn btn-primary btn-block" onclick="docStartManualCheck()">Check Details</button>
  </main>`;
}

function renderDocAnalyzing(title){
  return `
  ${docHeader(title,'Please wait a moment…', "docGoStep('landing')")}
  <main>
    <ul class="proc-list" id="docProcList">
      ${docState.analyzeSteps.map(s=>`<li><span class="dot">•</span> ${s}</li>`).join('')}
    </ul>
  </main>`;
}

function renderDocResult(){
  const r = docState.result;
  const meta = DOC_STATUS_META[r.status];
  const matchedProperty = r.matchedPropertyId ? PROPERTIES.find(p=>p.id===r.matchedPropertyId) : null;
  const backAction = docState.historyIndex!=null ? "docGoStep('history')" : "openVerifyDocument()";

  return `
  ${docHeader('Document Result', r.docType, backAction)}
  <main>
    <div class="vprop">
      <div class="thumb" style="display:flex;align-items:center;justify-content:center;font-size:22px;">${r.hasFile ? (r.fileMeta && r.fileMeta.type==='application/pdf'?'📄':'🖼️') : '✍️'}</div>
      <div>
        <div class="t">${r.docType}</div>
        <div class="l">${r.method==='upload' ? 'Checked via document upload' : 'Checked via manual entry'}</div>
        ${r.fields.documentNumber?`<div class="l">Doc. No. ${r.fields.documentNumber}</div>`:''}
      </div>
    </div>

    <div class="assess-banner assess-${meta.tone}">
      <div class="assess-icon" style="color:var(--${meta.tone})">${meta.icon}</div>
      <div class="assess-title">${meta.label}</div>
      <div class="assess-sub">${meta.blurb}</div>
      <div class="assess-sub" style="margin-top:6px;font-style:italic;">Assessment based on available checks</div>
    </div>

    ${r.reasons.length ? `<div class="section-title">Issues Found</div>
    <div class="vcat">${r.reasons.map(x=>`<div class="check-item"><span class="mark" style="color:var(--warn);">⚠</span><span>${x}</span></div>`).join('')}</div>` : ''}

    <div class="section-title">Checks Performed</div>
    <div class="vcat">${r.checks.map(c=>`<div class="check-item"><span class="mark" style="color:${c.ok===true?'var(--ok)':c.ok===false?'var(--bad)':'var(--mute)'}">${c.ok===true?'✓':c.ok===false?'⚠':'–'}</span><span>${c.text}</span></div>`).join('')}</div>

    ${matchedProperty ? `
    <div class="section-title">Possible Matching Property</div>
    <div class="vprop">
      <div class="thumb"></div>
      <div>
        <div class="t">${matchedProperty.title}</div>
        <div class="l">${matchedProperty.area} · ${matchedProperty.plot}</div>
        <div class="l">Owner on record: ${matchedProperty.owner}</div>
      </div>
    </div>
    <div class="action-row">
      <button class="btn btn-outline" onclick="nav('detail','${matchedProperty.id}')">View Property</button>
      <button class="btn btn-primary" onclick="nav('verify','${matchedProperty.id}')">Verify This Property</button>
    </div>
    <div class="auth-note">This is a possible match based on shared details, not a confirmed link between this document and the property.</div>
    ` : ''}

    <div class="section-title">Limitations</div>
    <div class="vcat">${r.limitations.map(x=>`<div class="check-item"><span class="mark" style="color:var(--mute);">–</span><span>${x}</span></div>`).join('')}</div>

    <div class="action-row">
      <button class="btn btn-outline" onclick="docGoStep('history')">My Document Checks</button>
      <button class="btn btn-primary" onclick="openVerifyDocument()">Check Another Document</button>
    </div>
  </main>`;
}

function renderDocHistoryList(){
  const rows = docHistory.map((r,i)=>{
    const meta = DOC_STATUS_META[r.status];
    const dateStr = new Date(r.timestamp).toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric'});
    return `<div class="vprop" style="margin-bottom:10px;">
      <div class="thumb" style="display:flex;align-items:center;justify-content:center;font-size:20px;">${r.hasFile?'📄':'✍️'}</div>
      <div style="flex:1;min-width:0;">
        <div class="t">${r.docType}</div>
        <div class="l">${dateStr} · ${r.method==='upload'?'Uploaded':'Manual entry'}</div>
        <span class="status-badge ${meta.badge}" style="margin-top:6px;">${meta.icon} ${meta.label}</span>
      </div>
      <div style="display:flex;flex-direction:column;gap:6px;flex-shrink:0;">
        <button class="btn btn-outline" style="padding:7px 10px;font-size:11px;" onclick="docViewHistory(${i})">View Result</button>
        <button class="btn btn-outline" style="padding:7px 10px;font-size:11px;color:var(--bad);border-color:var(--bad);" onclick="docDeleteHistory(${i})">Delete</button>
      </div>
    </div>`;
  }).join('') || `<div class="empty">No document checks yet. Upload a document or enter details manually to get started.</div>`;

  return `
  ${docHeader('My Document Checks', null, "docGoStep('landing')")}
  <main>${rows}</main>`;
}
