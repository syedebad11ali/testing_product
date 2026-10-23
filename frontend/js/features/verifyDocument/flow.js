/* features/verifyDocument/flow.js — 'Verify Your Document' wizard controller: step transitions, file handling, OCR run, history. */
import { nav, render } from '../../app/router.js';
import { SAMPLES_URL } from '../../config.js';
import { buildAutomaticResult, runDocumentChecks } from '../../domain/documentVerification.js';
import Extraction from '../../domain/extraction.js';
import { isCameraSupported, stopDocumentCamera } from './camera.js';
import { assessImageQualityFromDataUrl, readPdfText, runRealOCR } from '../../services/ocr.js';
import { docHistory, docState, freshDocState, resetDocState, saveDocHistory, state } from '../../state/store.js';

export function openVerifyDocument(){ stopDocumentCamera(); resetDocState(); nav('verify-document'); }

export function openReportEvidenceUpload(){
  stopDocumentCamera();
  resetDocState();
  docState.method = 'upload';
  docState.docType = 'Property Evidence';
  state.view = 'verify-document';
  state.propId = null;
  docState.step = 'autotype';
  render();
  window.scrollTo(0,0);
}

export function openReportEvidenceCamera(){
  stopDocumentCamera();
  resetDocState();
  docState.method = 'camera';
  docState.docType = 'Property Evidence';
  docState.cameraPhase = isCameraSupported() ? 'requesting' : 'unavailable';
  state.view = 'verify-document';
  state.propId = null;
  docState.step = 'camera';
  render();
  window.scrollTo(0,0);
}

export function docGoStep(step){ if(docState.step==='camera' && step!=='camera') stopDocumentCamera(); docState.step = step; render(); window.scrollTo(0,0); }

/* Upload and Camera are the PRIMARY automatic path: no document-type
   selection and no manual-field form is shown for either of them
   anymore — they go straight into the OCR pipeline (see
   startAutomaticVerification). "Enter Details Manually" is kept as a
   clearly secondary fallback and is the only path that still asks the
   user to pick a document type first, since that old flow depends on it. */
export function docPickMethod(method){
  stopDocumentCamera();
  docState.method=method; docState.docType=null; docState.file=null; docState.fields={};
  docState.fileError=null; docState.formError=null; docState.cameraPhase=null;
  docState.capturedImage=null; docState.cameraError=null;
  docState.extraction=null; docState.ocrText=''; docState.ocrProgress=0; docState.ocrPhaseLabel='';
  docState.showNotVerifiedModal=false;
  docState.typeKey=null;
  if(method==='camera' || method==='upload'){ docGoStep('autotype'); }
  else { docGoStep('type'); }
}

export function docPickAutoType(key){
  docState.typeKey=key;
  if(docState.method==='camera'){ docState.cameraPhase = isCameraSupported() ? 'requesting' : 'unavailable'; docGoStep('camera'); }
  else if(docState.method==='sample'){ docLoadSample(docState.pendingSample); }
  else { docGoStep('upload'); }
}

export function docPickType(type){
  docState.docType=type; docState.fields={};
  docGoStep('manual'); // only the manual fallback still reaches this screen
}

export function docSetField(key,val){ docState.fields[key]=val; }

export function docHandleFile(el){
  const file = el.files && el.files[0]; if(!file) return;
  const nameOk = /\.(pdf|jpe?g|png)$/i.test(file.name);
  const typeOk = ['application/pdf','image/jpeg','image/jpg','image/png'].includes(file.type);
  if(!nameOk && !typeOk){ docState.fileError='Unsupported file. Please upload a PDF, JPG or PNG.'; render(); return; }
  if(file.size===0){ docState.fileError='This file appears to be empty. Please choose a different file.'; render(); return; }
  if(file.size > 15*1024*1024){ docState.fileError='File too large. Please upload a file under 15 MB.'; render(); return; }
  docState.fileError=null;
  const meta = {name:file.name, size:file.size, type:file.type};
  if(file.type.startsWith('image/')){
    const reader = new FileReader();
    reader.onload = e=>{ docState.file = Object.assign({},meta,{dataUrl:e.target.result}); startAutomaticVerification(); };
    reader.onerror = ()=>{ docState.fileError='We could not read this image. Try a clearer scan or use Enter Details Manually.'; docState.file=null; render(); };
    reader.readAsDataURL(file);
  } else {
    const r2 = new FileReader();
    r2.onload = e=>{ docState.file = Object.assign({},meta,{bytes:new Uint8Array(e.target.result)}); startAutomaticVerification(); };
    r2.onerror = ()=>{ docState.fileError='We could not read this file.'; render(); };
    r2.readAsArrayBuffer(file);
  }
}

export function docRemoveFile(){ docState.file=null; docState.fileError=null; docState.extraction=null; render(); }

function docTickProcList(){
  const list = document.getElementById('docProcList');
  if(!list) return;
  const items = list.querySelectorAll('li');
  const item = items[docState.analyzeProgress-1];
  if(item){ item.classList.add('done'); const dot=item.querySelector('.dot'); if(dot) dot.textContent='✓'; }
}

export function docStartSample(typeKey, base, variant, ext){
  docState.method='sample'; docState.typeKey=typeKey; docState.pendingSample={base:base, variant:variant, ext:ext};
  docLoadSample(docState.pendingSample);
}

async function docLoadSample(sm){
  try{
    const name = sm.base+'_'+sm.variant+'.'+sm.ext;
    const resp = await fetch(SAMPLES_URL+name);
    if(!resp.ok) throw new Error('sample not found');
    const blob = await resp.blob();
    const isPdf = sm.ext==='pdf';
    const file = {name, size:blob.size, type: isPdf?'application/pdf':(sm.ext==='jpg'?'image/jpeg':'image/png')};
    if(isPdf){ file.bytes = new Uint8Array(await blob.arrayBuffer()); }
    else { file.dataUrl = await new Promise((res,rej)=>{ const r=new FileReader(); r.onload=e=>res(e.target.result); r.onerror=rej; r.readAsDataURL(blob); }); }
    docState.file = file;
    startAutomaticVerification();
  }catch(e){
    docState.method=null;
    docState.fileError='Could not load the sample ('+e.message+'). Sample documents need the site to be served over http(s), not opened as a file.';
    docGoStep('upload');
  }
}

export function docStartManualCheck(){
  const hasAny = Object.values(docState.fields).some(v=>v && v.trim && v.trim());
  if(!hasAny){ docState.formError='Please enter at least the owner name and one property reference before checking.'; render(); return; }
  docState.formError=null;
  docState.analyzeSteps = ['Checking field completeness…','Checking internal consistency…','Comparing available property records…','Identifying conflicts…','Preparing assessment…'];
  docState.analyzeProgress = 0;
  docGoStep('manual-analyzing');
  const timer = setInterval(()=>{
    docState.analyzeProgress++; docTickProcList();
    if(docState.analyzeProgress >= docState.analyzeSteps.length){
      clearInterval(timer);
      setTimeout(()=>{
        docState.result = Object.assign({pipeline:'manual'}, runDocumentChecks(docState.docType, docState.fields, false, null));
        docHistory.unshift(docState.result); saveDocHistory();
        docState.historyIndex = null;
        docGoStep('manual-result');
      }, 350);
    }
  }, 420);
}

export function docViewHistory(i){ docState.historyIndex=i; docState.result=docHistory[i]; docGoStep(docHistory[i].method==='upload'?'result':'manual-result'); }

export function docDeleteHistory(i){ docHistory.splice(i,1); saveDocHistory(); render(); }

export async function startAutomaticVerification(){
  const f = docState.file;
  if(!f){ docState.fileError='Please upload a document first, or switch to Enter Details Manually.'; render(); return; }
  docState.extraction = null; docState.ocrText=''; docState.ocrProgress = 0;
  docState.ocrPhaseLabel = 'Reading document…';
  docGoStep('ocr-analyzing');

  if(f.type === 'application/pdf'){
    try{
      const text = await readPdfText(f);
      if(text.replace(/\s/g,'').length < 30){ finishWithOcrFailure('This PDF has no readable text layer (it looks like a scan). Please upload a JPG/PNG photo of the page instead.'); return; }
      finishOcrWithText(text, 'pdf-text');
    }catch(err){
      finishWithOcrFailure('The PDF could not be read ('+(err&&err.message?err.message:'error')+'). Please upload a JPG or PNG photo of the document instead.');
    }
    return;
  }
  assessImageQualityFromDataUrl(f.dataUrl, (qualityOk)=>{
    if(!qualityOk){ finishWithOcrFailure('The image is too dark, too bright, blank, or too low-resolution to read clearly. Please try a clearer photo.'); return; }
    runRealOCR(f.dataUrl);
  });
}

export function finishWithOcrFailure(message){
  if(state.view!=='verify-document') return; // user navigated away mid-OCR
  docState.result = {pipeline:'auto', status:'ocr_failed', message, extraction:docState.extraction, ocrText:docState.ocrText||'', hasFile:true, fileMeta:docState.file, timestamp:Date.now()};
  docState.showNotVerifiedModal = false;
  docGoStep('result');
}

export function finishOcrWithText(text, source){
  if(state.view!=='verify-document') return;
  docState.ocrText = text || '';
  const extraction = Extraction.parseDocumentText(docState.ocrText, docState.typeKey||'other');
  docState.extraction = extraction;
  const meaningfulChars = docState.ocrText.replace(/\s/g,'').length;
  if(meaningfulChars < 15 || !extraction.profile.fields.some(f=>extraction[({name:'ownerName',cnic:'cnic',plot:'plotNumber',survey:'surveyNumber',address:'address',approvedArea:'approvedArea',paymentStatus:'paymentStatus'})[f]].found)){
    finishWithOcrFailure('We could not extract enough readable information from this document to perform the available checks. Please try a clearer photo, or use Enter Details Manually.');
    return;
  }
  const result = buildAutomaticResult(extraction, docState.file, source);
  docState.result = result;
  docHistory.unshift(result); saveDocHistory();
  docState.historyIndex = null;
  docState.showNotVerifiedModal = (result.status==='not_verified' || result.status==='suspicious');
  docGoStep('result');
}
