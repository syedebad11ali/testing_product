/* features/verifyDocument/camera.js — Browser camera capture for documents: permission, live view, review, quality checks. */
import { render } from '../../app/router.js';
import { escapeHtml } from '../../core/html.js';
import { docGoStep, startAutomaticVerification } from './flow.js';
import { docState } from '../../state/store.js';

/* ---------- SCAN / CAPTURE DOCUMENT (browser camera) ----------
   Uses navigator.mediaDevices.getUserMedia — a plain web API, no
   React Native or third-party camera library. A captured frame is
   converted to the same {name,size,type,dataUrl} shape docHandleFile()
   produces, so it enters the identical upload-review-and-analyze
   screen and the identical runDocumentChecks() pipeline. */
export function isCameraSupported(){
  return !!(navigator.mediaDevices && typeof navigator.mediaDevices.getUserMedia === 'function');
}

export function renderDocCamera(){
  switch(docState.cameraPhase){
    case 'live': return renderDocCameraLive();
    case 'denied': return renderDocCameraDenied();
    case 'unavailable': return renderDocCameraUnavailable();
    case 'review': return renderDocCameraReview();
    case 'poor-quality': return renderDocCameraPoorQuality();
    default: return renderDocCameraPermission();
  }
}

function nativeCameraInputHtml(){
  return `
    <input
      type="file"
      id="docCameraCaptureInput"
      accept="image/*"
      capture="environment"
      style="display:none"
      onchange="docHandleCameraCapture(this)"
    >
  `;
}

/* Compact top bar used for every full-viewport camera screen (in place
   of the large docHeader() block) so the header claims minimal vertical
   space, leaving the rest of the viewport for the video/preview area
   and keeping the action buttons below always on-screen. */
function camHeader(title, subtitle, backAction){
  return `<div class="cam-topbar">
    <button class="icon-btn" onclick="${backAction}" aria-label="Back"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m15 18-6-6 6-6"/></svg></button>
    <div class="cam-topbar-text">
      <div class="cam-topbar-title">${title}</div>
      ${subtitle?`<div class="cam-topbar-sub">${subtitle}</div>`:''}
    </div>
  </div>`;
}

function renderDocCameraPermission(){
  return `
  <div class="cam-fullscreen">
  ${camHeader('Scan / Capture Document', docState.docType, "docGoStep('landing')")}
  <div class="cam-fullscreen-body">
    <div class="doc-option-card" style="cursor:default;">
      <div class="doc-option-icon">📷</div>
      <h3>Use Your Camera</h3>
      <p>Open the camera to capture a clear photo of your document.</p>

      <button class="btn btn-primary btn-block" style="margin-top:0;" onclick="startDocumentCamera()">
        Open Live Camera
      </button>

      <label class="btn btn-outline btn-block cam-native-btn" for="docCameraCaptureInput">
        📸 Take Photo
      </label>

      <div style="font-size:11px;color:var(--sub);line-height:1.45;margin-top:10px;">
        On phones, <strong>Take Photo</strong> can open the device camera directly
        if live camera preview is unavailable.
      </div>
    </div>

    ${nativeCameraInputHtml()}

    <div class="camera-help-card">
      <strong>For the clearest result</strong>
      <span>Place the document on a flat surface, keep all four corners visible, and use good lighting.</span>
    </div>

    <button class="btn btn-outline btn-block" onclick="docGoStep('upload')">Choose an Existing Photo Instead</button>
    <button class="btn btn-link btn-block" onclick="docGoStep('manual')">Enter Details Manually</button>
  </div>
  </div>`;
}

function renderDocCameraDenied(){
  return `
  <div class="cam-fullscreen">
  ${camHeader('Camera Access Blocked', docState.docType, "docGoStep('landing')")}
  <div class="cam-fullscreen-body">
    <div class="doc-option-card" style="cursor:default;">
      <div class="doc-option-icon">🚫</div>
      <h3>Live Camera Unavailable</h3>
      <p>${escapeHtml(docState.cameraError || 'Your browser did not allow the live camera preview.')}</p>

      <label class="btn btn-primary btn-block cam-native-btn" for="docCameraCaptureInput">
        📸 Take Photo
      </label>

      <button class="btn btn-outline btn-block" onclick="docGoStep('upload')">Upload an Existing Photo</button>
      <button class="btn btn-outline btn-block" onclick="docGoStep('manual')">Enter Details Manually</button>

      <div class="camera-help-card" style="margin-top:12px;text-align:left;">
        <strong>Why this happens</strong>
        <span>Live camera access can be blocked by browser privacy settings, an embedded preview, or an insecure page. The phone's camera upload is provided as a fallback.</span>
      </div>
    </div>

    ${nativeCameraInputHtml()}
  </div>
  </div>`;
}

function renderDocCameraUnavailable(){
  return `
  <div class="cam-fullscreen">
  ${camHeader('Camera Not Available', docState.docType, "docGoStep('landing')")}
  <div class="cam-fullscreen-body">
    <div class="doc-option-card" style="cursor:default;">
      <div class="doc-option-icon">📷</div>
      <h3>Use Your Device Camera</h3>
      <p>Live preview is unavailable here, but you can still take a photo with your device camera and use it for document verification.</p>

      <label class="btn btn-primary btn-block cam-native-btn" for="docCameraCaptureInput">
        📸 Take Photo
      </label>

      <button class="btn btn-outline btn-block" onclick="docGoStep('upload')">Upload an Existing Photo</button>
      <button class="btn btn-outline btn-block" onclick="docGoStep('manual')">Enter Details Manually</button>
    </div>

    ${nativeCameraInputHtml()}

    <div class="camera-help-card">
      <strong>Live camera note</strong>
      <span>For live preview, open the deployed site over HTTPS or run it on localhost. The Take Photo option is designed as the mobile fallback.</span>
    </div>
  </div>
  </div>`;
}

function renderDocCameraLive(){
  return `
  <div class="cam-fullscreen">
  ${camHeader('Scan Document', docState.docType, "closeDocumentCamera()")}
  <div class="cam-fullscreen-body">
    <div class="cam-wrap">
      <video id="docCameraVideo" autoplay playsinline muted></video>
      <div class="cam-overlay"><div class="cam-frame">
        <span class="cam-corner tl"></span><span class="cam-corner tr"></span>
        <span class="cam-corner bl"></span><span class="cam-corner br"></span>
        <div class="cam-frame-label">Fit the whole document inside the frame</div>
      </div></div>
      ${docState.cameraError?`<div class="cam-error">${escapeHtml(docState.cameraError)}</div>`:''}
    </div>

    <div class="cam-hint">
      <strong>Position the document inside the frame</strong>
      Make sure all four corners are visible and the text is clear.
    </div>

    <div class="cam-controls">
      <button class="cam-btn" onclick="closeDocumentCamera()" aria-label="Close">✕</button>
      <button class="cam-capture" onclick="captureDocumentFrame()" aria-label="Capture document" title="Capture document"></button>
      <button class="cam-btn" id="camSwitchBtn" style="visibility:hidden;" onclick="switchDocumentCamera()" aria-label="Switch camera">⟳</button>
    </div>

    <div class="cam-secondary-actions">
      <label class="btn btn-outline cam-native-btn" for="docCameraCaptureInput">📸 Use Device Camera</label>
      <button class="btn btn-link" onclick="docGoStep('upload')">Choose Existing Photo</button>
    </div>

    ${nativeCameraInputHtml()}
  </div>
  </div>`;
}

function renderDocCameraReview(){
  return `
  <div class="cam-fullscreen">
  ${camHeader('Review Document', docState.docType, "closeDocumentCamera()")}
  <div class="cam-fullscreen-body">
    <div class="camera-review-card">
      <img class="doc-preview-img" src="${escapeHtml(docState.capturedImage || '')}" alt="Captured document preview">
      <div class="camera-review-meta">
        <strong>Check the photo before continuing</strong>
        <span>Make sure the document is fully visible and the text is readable.</span>
      </div>
    </div>
    <div class="action-row">
      <button class="btn btn-outline" onclick="retakeDocumentCapture()">Retake</button>
      <button class="btn btn-primary" onclick="useCapturedDocument()">Use This Document</button>
    </div>
  </div>
  </div>`;
}

function renderDocCameraPoorQuality(){
  return `
  <div class="cam-fullscreen">
  ${camHeader('Image Too Difficult to Read', docState.docType, "closeDocumentCamera()")}
  <div class="cam-fullscreen-body">
    <div class="doc-option-card" style="cursor:default;">
      <div class="doc-option-icon">⚠️</div>
      <h3>Try a Clearer Photo</h3>
      <p>The captured image appears too dark, blank, or unclear for a useful check.</p>
      <button class="btn btn-primary btn-block" onclick="retakeDocumentCapture()">Retake Photo</button>
      <label class="btn btn-outline btn-block cam-native-btn" for="docCameraCaptureInput">📸 Take Photo With Device Camera</label>
    </div>
    ${nativeCameraInputHtml()}
  </div>
  </div>`;
}

function handleCameraError(err){
  const name = err && err.name;
  docState.cameraStream = null;

  if(name==='NotAllowedError' || name==='PermissionDeniedError' || name==='SecurityError'){
    docState.cameraPhase='denied';
    docState.cameraError='Camera permission was denied or blocked.';
  } else if(name==='NotFoundError' || name==='DevicesNotFoundError'){
    docState.cameraPhase='unavailable';
    docState.cameraError='No camera device was found.';
  } else if(name==='NotReadableError'){
    docState.cameraPhase='denied';
    docState.cameraError='The camera is already in use by another app or browser tab.';
  } else if(name==='OverconstrainedError'){
    // Retry once with a generic camera constraint instead of failing outright.
    try{
      navigator.mediaDevices.getUserMedia({video:true,audio:false}).then(handleCameraStream).catch(finalCameraError);
      return;
    }catch(e){}
    docState.cameraPhase='unavailable';
    docState.cameraError='The selected camera configuration is not available.';
  } else {
    docState.cameraPhase='denied';
    docState.cameraError='The live camera could not be started in this browser.';
  }

  render();
}

function finalCameraError(err){
  const name = err && err.name;
  docState.cameraStream = null;
  if(name==='NotFoundError' || name==='DevicesNotFoundError'){
    docState.cameraPhase='unavailable';
    docState.cameraError='No camera device was found.';
  }else{
    docState.cameraPhase='denied';
    docState.cameraError='The live camera could not be started. Use Take Photo instead.';
  }
  render();
}

function handleCameraStream(stream){
  docState.cameraStream = stream;
  const video = document.getElementById('docCameraVideo');

  if(!video){
    stream.getTracks().forEach(t=>t.stop());
    docState.cameraStream = null;
    docState.cameraPhase='unavailable';
    docState.cameraError='Camera preview could not be mounted. Use Take Photo instead.';
    render();
    return;
  }

  video.muted = true;
  video.autoplay = true;
  video.playsInline = true;
  video.setAttribute('playsinline','');
  video.setAttribute('webkit-playsinline','');
  video.srcObject = stream;

  const playVideo = ()=>{
    const p = video.play();
    if(p && typeof p.catch==='function') p.catch(()=>{});
  };

  if(video.readyState >= 1) playVideo();
  else video.addEventListener('loadedmetadata', playVideo, {once:true});

  if(navigator.mediaDevices.enumerateDevices){
    navigator.mediaDevices.enumerateDevices().then(devices=>{
      const count = devices.filter(d=>d.kind==='videoinput').length;
      const btn = document.getElementById('camSwitchBtn');
      if(btn) btn.style.visibility = count > 1 ? 'visible' : 'hidden';
    }).catch(()=>{});
  }
}

export function startDocumentCamera(){
  if(!isCameraSupported()){
    docState.cameraPhase='unavailable';
    docState.cameraError='This browser does not provide live camera access.';
    render();
    return;
  }

  docState.cameraError = null;
  docState.cameraPhase = 'live';
  render();

  // Give the browser one paint cycle to mount the video element.
  requestAnimationFrame(()=>{
    const constraints = {
      video:{
        facingMode:{ideal:docState.cameraFacing || 'environment'},
        width:{ideal:1280},
        height:{ideal:720}
      },
      audio:false
    };

    navigator.mediaDevices.getUserMedia(constraints)
      .then(handleCameraStream)
      .catch(handleCameraError);
  });
}

export function switchDocumentCamera(){
  if(!isCameraSupported()) return;

  const newFacing = docState.cameraFacing==='environment' ? 'user' : 'environment';

  navigator.mediaDevices.getUserMedia({
    video:{
      facingMode:{ideal:newFacing},
      width:{ideal:1280},
      height:{ideal:720}
    },
    audio:false
  }).then(newStream=>{
    if(docState.cameraStream) docState.cameraStream.getTracks().forEach(t=>t.stop());

    docState.cameraStream = newStream;
    docState.cameraFacing = newFacing;

    const video = document.getElementById('docCameraVideo');
    if(video){
      video.srcObject = newStream;
      video.muted = true;
      video.play().catch(()=>{});
    }
  }).catch(()=>{});
}

export function stopDocumentCamera(){
  if(docState.cameraStream){
    docState.cameraStream.getTracks().forEach(t=>t.stop());
    docState.cameraStream = null;
  }

  const video = document.getElementById('docCameraVideo');
  if(video && video.srcObject){
    try{ video.pause(); }catch(e){}
    video.srcObject = null;
  }
}

export function assessCaptureQuality(canvas){
  try{
    if(!canvas.width || !canvas.height || canvas.width<50 || canvas.height<50) return false;

    const sample = document.createElement('canvas');
    sample.width=40; sample.height=40;
    const ctx=sample.getContext('2d', {willReadFrequently:true});
    if(!ctx) return true;

    ctx.drawImage(canvas,0,0,40,40);
    const data=ctx.getImageData(0,0,40,40).data;
    let sum=0, sumSq=0, n=0;

    for(let i=0;i<data.length;i+=4){
      const lum=(data[i]+data[i+1]+data[i+2])/3;
      sum+=lum; sumSq+=lum*lum; n++;
    }

    const mean=sum/n;
    const variance=sumSq/n - mean*mean;

    // Also reject frames that are almost completely black.
    return mean > 12 && variance > 15;
  }catch(e){
    return true;
  }
}

export function captureDocumentFrame(){
  const video = document.getElementById('docCameraVideo');

  if(!video || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA || !video.videoWidth){
    docState.cameraError='Camera is still starting. Please wait a moment and try again.';
    render();
    return;
  }

  const canvas=document.createElement('canvas');
  canvas.width=video.videoWidth;
  canvas.height=video.videoHeight;

  const ctx=canvas.getContext('2d');
  if(!ctx){
    docState.cameraError='Your browser could not capture the camera frame. Use Take Photo instead.';
    render();
    return;
  }

  ctx.drawImage(video,0,0,canvas.width,canvas.height);

  let dataUrl;
  try{
    dataUrl=canvas.toDataURL('image/jpeg',0.9);
  }catch(e){
    docState.cameraError='Capture failed. Use Take Photo instead.';
    render();
    return;
  }

  if(!dataUrl || dataUrl.length<100){
    docState.cameraError='Capture failed. Please try again.';
    render();
    return;
  }

  const qualityOk=assessCaptureQuality(canvas);

  stopDocumentCamera();
  docState.capturedImage=dataUrl;
  docState.cameraError=null;
  docState.cameraPhase=qualityOk ? 'review' : 'poor-quality';
  render();
}

export function docHandleCameraCapture(el){
  const file=el && el.files && el.files[0];
  if(!file) return;

  const allowedType=file.type && file.type.startsWith('image/');
  const allowedName=/\.(jpe?g|png|webp|heic|heif)$/i.test(file.name || '');

  if(!allowedType && !allowedName){
    docState.cameraError='Please capture or choose an image of the document.';
    render();
    return;
  }

  if(file.size===0){
    docState.cameraError='The captured image is empty. Please take the photo again.';
    render();
    return;
  }

  if(file.size>15*1024*1024){
    docState.cameraError='The captured image is larger than 15 MB.';
    render();
    return;
  }

  stopDocumentCamera();
  docState.fileError=null;

  const reader=new FileReader();
  reader.onload=e=>{
    docState.capturedImage=e.target.result;
    docState.cameraError=null;

    // Basic quality check for the native camera image too.
    const img=new Image();
    img.onload=()=>{
      const canvas=document.createElement('canvas');
      canvas.width=img.naturalWidth || img.width;
      canvas.height=img.naturalHeight || img.height;
      const ctx=canvas.getContext('2d');
      if(ctx) ctx.drawImage(img,0,0,canvas.width,canvas.height);

      const qualityOk=ctx ? assessCaptureQuality(canvas) : true;
      docState.cameraPhase=qualityOk ? 'review' : 'poor-quality';
      render();
    };
    img.onerror=()=>{
      docState.cameraPhase='review';
      render();
    };
    img.src=e.target.result;
  };
  reader.onerror=()=>{
    docState.cameraError='We could not read the captured photo. Please try again.';
    docState.cameraPhase='unavailable';
    render();
  };
  reader.readAsDataURL(file);

  // Let the same input be triggered again later.
  try{ el.value=''; }catch(e){}
}

export function retakeDocumentCapture(){
  docState.capturedImage=null;
  docState.cameraError=null;
  startDocumentCamera();
}

export function closeDocumentCamera(){
  stopDocumentCamera();
  docState.cameraPhase=null;
  docState.capturedImage=null;
  docState.cameraError=null;
  docGoStep('landing');
}

export function useCapturedDocument(){
  const dataUrl=docState.capturedImage;
  if(!dataUrl) return;

  const approxBytes=Math.round((dataUrl.length - dataUrl.indexOf(',') - 1)*3/4);

  docState.file={
    name:'Camera_Capture_'+Date.now()+'.jpg',
    size:approxBytes,
    type:'image/jpeg',
    dataUrl
  };

  docState.method='camera';
  docState.capturedImage=null;
  docState.cameraPhase=null;
  docState.fileError=null;

  // Send the captured image into the SAME automatic OCR pipeline used by uploads.
  startAutomaticVerification();
}
