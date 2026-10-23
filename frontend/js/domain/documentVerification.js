/* domain/documentVerification.js — Pure document-verification rules: match extracted fields to records and decide a status. */
import { DEMO_PROPERTIES, DOC_FIELD_DEFS, DOC_REQUIRED_FIELDS } from '../data/documentTypes.js';
import { PROPERTIES } from '../data/properties.js';
import Extraction from './extraction.js';
import { state } from '../state/store.js';

function docNormalize(s){ return (s||'').toString().toLowerCase().replace(/[^a-z0-9]/g,''); }

/* Never declares a definite link — only a possible match, per product spec. */
function findMatchingProperty(fields){
  let best=null, bestScore=0;
  const plotN=docNormalize(fields.plotNumber), ownerN=docNormalize(fields.ownerName),
        surveyN=docNormalize(fields.surveyNumber), addrN=docNormalize(fields.propertyAddress);
  PROPERTIES.forEach(p=>{
    let score=0;
    const pPlotN=docNormalize(p.plot), pOwnerN=docNormalize(p.owner), pSurveyN=p.survey!=='—'?docNormalize(p.survey):'';
    if(plotN && pPlotN.includes(plotN)) score+=2;
    if(ownerN && pOwnerN===ownerN) score+=2;
    if(surveyN && pSurveyN && pSurveyN===surveyN) score+=2;
    if(addrN && pPlotN.includes(addrN)) score+=1;
    if(fields.area && docNormalize(fields.area)===docNormalize(p.area)) score+=1;
    if(score>bestScore){ bestScore=score; best=p; }
  });
  return bestScore>=2 ? best : null;
}

/* Deterministic demo authenticity engine. Modular on purpose: a real
   OCR / image-forensics / registry-API backend can replace this function
   body later without any change to the views below. */
export function runDocumentChecks(docType, fields, hasFile, fileMeta){
  const checks=[], reasons=[];
  if(hasFile){
    checks.push({ok:true, text:'Document file readable'});
    if(fileMeta && fileMeta.size < 4*1024){
      checks.push({ok:false, text:'File size unusually small for a scanned document'});
      reasons.push('The uploaded file is very small, which can indicate a low-quality scan, a cropped image, or an incomplete file.');
    } else {
      checks.push({ok:true, text:'File size within expected range'});
    }
    checks.push({ok:null, text:'Visual/image tampering analysis requires a dedicated forensics service — not available in this demo'});
  } else {
    checks.push({ok:null, text:'No document file provided — visual and file-structure checks were not run'});
  }

  const required = DOC_REQUIRED_FIELDS[docType] || ['ownerName'];
  const missing = required.filter(f=>!fields[f] || !fields[f].trim());
  if(missing.length===0){ checks.push({ok:true, text:'Required fields for this document type are present'}); }
  else {
    checks.push({ok:false, text:'Missing expected fields: '+missing.map(f=>DOC_FIELD_DEFS[f].label).join(', ')});
    reasons.push('Some expected fields for a '+docType+' were left blank.');
  }

  const matchedProperty = findMatchingProperty(fields);
  let ownerMismatch=false, plotMismatch=false;
  if(matchedProperty){
    checks.push({ok:true, text:'A possible matching property was found in available records'});
    if(fields.ownerName && fields.ownerName.trim()){
      if(docNormalize(fields.ownerName)!==docNormalize(matchedProperty.owner)){
        ownerMismatch=true;
        checks.push({ok:false, text:"Owner name differs from the available property record"});
        reasons.push('Entered owner "'+fields.ownerName+'" does not match the recorded owner "'+matchedProperty.owner+'" for this property.');
      } else checks.push({ok:true, text:'Owner name matches available record'});
    }
    if(fields.plotNumber && fields.plotNumber.trim()){
      if(!docNormalize(matchedProperty.plot).includes(docNormalize(fields.plotNumber))){
        plotMismatch=true;
        checks.push({ok:false, text:'Property reference does not match the available record'});
        reasons.push('Entered plot/reference "'+fields.plotNumber+'" does not match the recorded reference "'+matchedProperty.plot+'".');
      } else checks.push({ok:true, text:'Property reference matches available record'});
    }
  } else {
    checks.push({ok:null, text:'No matching property could be found in available records — comparison is limited'});
  }
  checks.push({ok:null, text:'Official land-registry or authority verification was not performed (unavailable in this demo)'});

  let status;
  const hasIssues = ownerMismatch || plotMismatch;
  if(!hasFile){
    // Manual entry can never be labelled Original — correct-looking typed details are not proof.
    status = hasIssues ? 'review_required' : 'unable_to_determine';
  } else if(hasIssues){
    status = 'potentially_forged';
  } else if(missing.length>0 || !matchedProperty){
    status = 'review_required';
  } else {
    status = 'likely_original';
  }

  const limitations=[];
  if(!hasFile) limitations.push('No document file was provided, so visual editing, file metadata, signatures and scanned alterations could not be inspected.');
  limitations.push('Official authentication was not performed. Confirm with the relevant authority or an appropriate verification service before relying on this result.');
  if(!matchedProperty) limitations.push('No matching property was found in the available demo records, so comparison was limited to internal consistency.');

  return {
    status, checks, reasons, limitations,
    matchedPropertyId: matchedProperty?matchedProperty.id:null,
    docType, fields: Object.assign({},fields), hasFile,
    fileMeta: fileMeta?{name:fileMeta.name,size:fileMeta.size,type:fileMeta.type}:null,
    method: hasFile?'upload':'manual',
    timestamp: Date.now()
  };
}

/* Automatic verification pipeline (pure functions).
   OCR/PDF text -> Extraction.parseDocumentText -> buildAutomaticResult. Parsed fields are what
   gets shown and compared; nothing is hard-coded. Unit-tested in tests/frontend/. */
export function maskCnic(digits){
  if(!digits || digits.length!==13) return digits || '';
  return digits.slice(0,5)+'-******'+digits.slice(11,12)+'-'+digits.slice(12);
}

function extractionToFields(extraction){
  return {
    ownerName: extraction.ownerName.found && !extraction.ownerName.conflict ? extraction.ownerName.display : '',
    plotNumber: extraction.plotNumber.found && !extraction.plotNumber.conflict ? extraction.plotNumber.display : '',
    cnic: extraction.cnic.found && !extraction.cnic.conflict ? extraction.cnic.value : '',
    documentNumber: ''
  };
}

export function allVerificationRecords(){ return DEMO_PROPERTIES.concat(PROPERTIES); }

/* Builds the result object from REAL extracted fields using the shared
   Extraction.decide() rules (the same function scripts/manifest-report.mjs
   runs against the real sample dataset). Not a proof of authenticity. */
export function buildAutomaticResult(extraction, fileMeta, source){
  const checks = [{ok:true, text:(source==='pdf-text'?'PDF text layer read directly':'Document image read by the OCR engine')}];
  const labels = {name:'Name', cnic:'CNIC', plot:'Plot number', survey:'Survey number', address:'Property address', approvedArea:'Approved area', paymentStatus:'Payment status'};
  const keyOf = {name:'ownerName', cnic:'cnic', plot:'plotNumber', survey:'surveyNumber', address:'address', approvedArea:'approvedArea', paymentStatus:'paymentStatus'};
  extraction.profile.fields.forEach(f=>{
    const fld = extraction[keyOf[f]];
    if(fld.conflict) checks.push({ok:false, text:labels[f]+' — conflicting values in the document: '+fld.values.join(' vs ')});
    else if(fld.found) checks.push({ok:true, text:labels[f]+' detected: '+(f==='cnic'?maskCnic(fld.value):fld.display)});
    else checks.push({ok:null, text:labels[f]+' was not detected in the document'});
  });
  const base = {pipeline:'auto', extraction, fields:extractionToFields(extraction), hasFile:true, fileMeta, method:'upload', timestamp:Date.now(), source:source||'ocr'};

  // Find the record to compare against (free search — no property context here).
  const records = allVerificationRecords();
  const matchInfo = Extraction.matchProperty(extraction, records);
  const matched = matchInfo.property;

  const conflicts = ['ownerName','plotNumber','cnic','surveyNumber'].filter(f=>extraction[f].conflict);
  if(!matched && !conflicts.length){
    const anyFound = extraction.profile.fields.some(f=>extraction[keyOf[f]].found);
    if(!anyFound) return Object.assign({}, base, {status:'unable_to_verify', checks, reasons:['No usable information could be read from the document.'], limitations:['Insufficient information was extracted to perform verification.'], matchedPropertyId:null});
    checks.push({ok:null, text:'No matching property was found in available records'});
    return Object.assign({}, base, {status:'not_verified', checks, reasons:['No property in the available records matches the information extracted from this document.'], limitations:['Comparison is limited to the records available in this application.'], matchedPropertyId:null, noMatch:true});
  }
  const d = Extraction.decide(extraction, matched, {ocr: source!=='pdf-text'});
  if(d.cmp){
    const lab = {name:'Name', cnic:'CNIC', plot:'Plot number', survey:'Survey number', address:'Address', approvedArea:'Approved area'};
    Object.keys(lab).forEach(k=>{ const st=d.cmp[k]; if(st && st!=='unknown') checks.push({ok: st==='match'?true:(st==='mismatch'||st==='conflict')?false:null, text: lab[k]+(st==='match'?' matches available record':st==='mismatch'?' does not match available record':st==='uncertain'?' could not be confirmed (possible OCR misread)':' — conflicting values')}); });
  }
  const limitations = ['Verified against available application records only. Official authentication has not been performed.'];
  if(extraction.profile.label==='Power of Attorney') limitations.push('The attorney\'s identity was not checked: no attorney reference exists in the available records.');
  if(source!=='pdf-text') limitations.push('Text was read by OCR, which can misread characters; uncertain characters are reported as unable to verify rather than as mismatches.');
  return Object.assign({}, base, {status:d.status, checks, reasons:d.reasons, limitations, matchedPropertyId:matched?matched.id:null});
}
