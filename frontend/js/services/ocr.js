/* services/ocr.js — Browser OCR (Tesseract) and PDF text-layer reading, plus image-quality checks. */
import { render } from '../app/router.js';
import Extraction from '../domain/extraction.js';
import { assessCaptureQuality } from '../features/verifyDocument/camera.js';
import { finishOcrWithText, finishWithOcrFailure } from '../features/verifyDocument/flow.js';
import { renderOcrProgressOnly } from '../features/verifyDocument/views.js';
import { docState } from '../state/store.js';

export function assessImageQualityFromDataUrl(dataUrl, cb){
  try{
    const img = new Image();
    img.onload = ()=>{
      try{
        const canvas = document.createElement('canvas');
        canvas.width = img.naturalWidth || img.width; canvas.height = img.naturalHeight || img.height;
        const ctx = canvas.getContext('2d');
        if(!ctx){ cb(true); return; }
        ctx.drawImage(img,0,0,canvas.width,canvas.height);
        cb(assessCaptureQuality(canvas));
      }catch(e){ cb(true); }
    };
    img.onerror = ()=>cb(true);
    img.src = dataUrl;
  }catch(e){ cb(true); }
}

function countFound(text, typeKey){
  const x = Extraction.parseDocumentText(text, typeKey||'other');
  const m = {name:'ownerName',cnic:'cnic',plot:'plotNumber',survey:'surveyNumber',address:'address',approvedArea:'approvedArea',paymentStatus:'paymentStatus'};
  return x.profile.fields.filter(f=>x[m[f]].found).length;
}

/* Real OCR. Pass 1 uses Tesseract's automatic page segmentation (PSM 3).
   Evidence from the sample set: PSM 3 reads most table layouts, but drops
   rows on some highlighted-field images where PSM 6 succeeds, so if pass 1
   finds fewer fields than the document type expects we run PSM 6 too and
   keep whichever pass extracted more fields. */
export async function runRealOCR(dataUrl){
  if(typeof Tesseract === 'undefined'){
    finishWithOcrFailure('The OCR engine could not be loaded (this needs an internet connection the first time). Please check your connection and try again, or use Enter Details Manually.');
    return;
  }
  docState.ocrPhaseLabel = 'Reading document…'; docState.ocrProgress = 0; render();
  let worker;
  try{
    worker = await Tesseract.createWorker('eng', 1, {logger(m){
      if(!m) return;
      if(m.status==='recognizing text'){ docState.ocrPhaseLabel='Extracting information…'; docState.ocrProgress=Math.round((m.progress||0)*100); }
      else if(m.status){ docState.ocrPhaseLabel=m.status.charAt(0).toUpperCase()+m.status.slice(1)+'…'; }
      renderOcrProgressOnly();
    }});
    await worker.setParameters({tessedit_pageseg_mode:'3'});
    let text = (await worker.recognize(dataUrl)).data.text || '';
    const expected = (Extraction.TYPE_PROFILES[docState.typeKey||'other']||Extraction.TYPE_PROFILES.other).fields.length;
    if(countFound(text, docState.typeKey) < expected){
      docState.ocrPhaseLabel='Re-reading with an alternate layout mode…'; renderOcrProgressOnly();
      await worker.setParameters({tessedit_pageseg_mode:'6'});
      const alt = (await worker.recognize(dataUrl)).data.text || '';
      if(countFound(alt, docState.typeKey) > countFound(text, docState.typeKey)) text = alt;
    }
    await worker.terminate();
    finishOcrWithText(text, 'ocr');
  }catch(err){
    try{ if(worker) await worker.terminate(); }catch(e){}
    finishWithOcrFailure('The document could not be processed ('+(err&&err.message?err.message:'OCR error')+'). Please try a clearer photo.');
  }
}

/* PDFs: read the embedded text layer with PDF.js (no OCR needed when the
   PDF has real text). If a PDF has no text layer (a scan), we say so —
   we do not pretend it was read. */
export async function readPdfText(f){
  if(typeof pdfjsLib === 'undefined') throw new Error('PDF reader could not be loaded');
  pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdn.jsdelivr.net/npm/pdfjs-dist@3.11.174/build/pdf.worker.min.js';
  const pdf = await pdfjsLib.getDocument({data: f.bytes}).promise;
  let out = '';
  for(let i=1;i<=Math.min(pdf.numPages,5);i++){
    const tc = await (await pdf.getPage(i)).getTextContent();
    // rebuild lines from text item positions so labels/values stay on their lines
    let lastY=null, line='';
    tc.items.forEach(it=>{ const y=Math.round(it.transform[5]); if(lastY!==null && Math.abs(y-lastY)>3){ out+=line.trim()+'\n'; line=''; } line+=it.str+' '; lastY=y; });
    out += line.trim()+'\n\n';
  }
  return out;
}
