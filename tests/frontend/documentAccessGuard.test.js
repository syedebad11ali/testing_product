import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { installDom } from './helpers/domStub.js';

/* G6.1a: document verification is an account feature, and the check lives INSIDE every action function, not only in the router.
 * Guests, signed-out visitors, an unreachable session and an unresolved session get the shared "Login required" dialog; the action
 * does nothing: no camera permission request (getUserMedia), no file read (FileReader), no sample download, no state change.
 * fetch, getUserMedia and FileReader are spies, so "nothing ran" is observed, not assumed. Registered users and admins are unchanged. */
const { document } = installDom();
globalThis.window.location = globalThis.location = { hash: '', pathname: '/', search: '' };
globalThis.history = { replaceState() {}, pushState() {} };
globalThis.requestAnimationFrame = (fn) => fn();
let dialogs = [];
document.activeElement = null;
document.removeEventListener = () => {};
document.body.appendChild = (node) => { dialogs.push(node); return node; };
const origCreate = document.createElement;
document.createElement = () => { const e = origCreate(); e.isConnected = true; e.remove = () => { e.isConnected = false; dialogs = dialogs.filter((d) => d !== e); }; return e; };

let fetchUrls = [], release = null, cameraRequests = 0, fileReads = 0;
function stubSession(user, { hold = false, fail = false } = {}) {
  globalThis.fetch = (url) => {
    fetchUrls.push(String(url));
    if (String(url) !== '/api/v1/auth/me') return Promise.resolve({ ok: true, status: 200, text: async () => '', blob: async () => ({ size: 1 }) });
    if (fail) return Promise.reject(new TypeError('offline'));
    const reply = { ok: true, status: 200, text: async () => JSON.stringify({ user }) };
    return hold ? new Promise((resolve) => { release = () => resolve(reply); }) : Promise.resolve(reply);
  };
}
Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { mediaDevices: { getUserMedia: () => { cameraRequests += 1; return new Promise(() => {}); } } } });
globalThis.FileReader = class { readAsDataURL() { fileReads += 1; } readAsArrayBuffer() { fileReads += 1; } };

const { openVerifyDocument, openReportEvidenceUpload, openReportEvidenceCamera, docGoStep, docPickMethod, docPickAutoType, docPickType,
  docHandleFile, docStartSample, docStartManualCheck, startAutomaticVerification } = await import('../../frontend/js/features/verifyDocument/flow.js');
const { startDocumentCamera, switchDocumentCamera, captureDocumentFrame, docHandleCameraCapture, useCapturedDocument } = await import('../../frontend/js/features/verifyDocument/camera.js');
const { ACTIONS } = await import('../../frontend/js/ui/actions.js');
const { state, docState, resetDocState } = await import('../../frontend/js/state/store.js');
const { resetSessionUser, loadSessionUser, isAccountSession } = await import('../../frontend/js/services/sessionUser.js');
const { showLoginRequired } = await import('../../frontend/js/features/loginPrompt.js');

const ROW = { id: 'u1', name: 'Sara', must_change_password: false };
const png = () => ({ files: [{ name: 'deed.png', type: 'image/png', size: 1234 }], value: '' });
const ACTION_CALLS = {
  openVerifyDocument: () => openVerifyDocument(),
  openReportEvidenceUpload: () => openReportEvidenceUpload(),
  openReportEvidenceCamera: () => openReportEvidenceCamera(),
  docGoStep_upload: () => docGoStep('upload'),
  docGoStep_camera: () => docGoStep('camera'),
  docPickMethod_upload: () => docPickMethod('upload'),
  docPickMethod_camera: () => docPickMethod('camera'),
  docPickMethod_manual: () => docPickMethod('manual'),
  docPickAutoType: () => docPickAutoType('cnic'),
  docPickType: () => docPickType('CNIC'),
  docHandleFile: () => docHandleFile(png()),
  docStartSample: () => docStartSample('sale_deed', 'sale_deed', 'matching', 'png'),
  docStartManualCheck: () => { docState.fields = { name: 'Ali' }; return docStartManualCheck(); },
  startAutomaticVerification: () => { docState.file = { name: 'x.png', size: 10, type: 'image/png', dataUrl: 'data:image/png;base64,AA==' }; return startAutomaticVerification(); },
  startDocumentCamera: () => startDocumentCamera(),
  switchDocumentCamera: () => switchDocumentCamera(),
  captureDocumentFrame: () => captureDocumentFrame(),
  docHandleCameraCapture: () => docHandleCameraCapture(png()),
  useCapturedDocument: () => { docState.capturedImage = 'data:image/jpeg;base64,AA=='; return useCapturedDocument(); },
};

function reset(user, opts) {
  resetSessionUser(); resetDocState(); fetchUrls = []; release = null; cameraRequests = 0; fileReads = 0;
  state.view = 'home'; state.propId = null;
  for (const d of [...dialogs]) d.remove();
  dialogs = [];
  stubSession(user, opts);
  showLoginRequired().close(); dialogs = [];   // the module keeps one dialog; close any left by an earlier test
}
for (const [name, user, opts] of [
  ['signed-out visitor', null, {}],
  ['guest', { ...ROW, role: 'guest' }, {}],
  ['session request fails (offline)', { ...ROW, role: 'user' }, { fail: true }],
]) {
  test(`${name}: every document action called DIRECTLY is refused with the login dialog and does nothing`, async () => {
    for (const [label, call] of Object.entries(ACTION_CALLS)) {
      reset(user, opts);
      const typeBefore = docState.typeKey;
      await call();
      assert.equal(dialogs.length, 1, `${label}: login dialog shown`);
      assert.equal(cameraRequests, 0, `${label}: camera permission requested`);
      assert.equal(fileReads, 0, `${label}: a file was read`);
      assert.deepEqual(fetchUrls.filter((u) => u !== '/api/v1/auth/me'), [], `${label}: extra request`);
      assert.equal(state.view, 'home', `${label}: view changed`);
      assert.equal(docState.step, 'landing', `${label}: wizard moved`);
      assert.equal(docState.typeKey, typeBefore, `${label}: type changed`);
      assert.equal(docState.method, null, `${label}: method changed`);
      assert.equal(docState.result, null, `${label}: a result appeared`);
    }
  });
}

test('the same actions through the registered action table (an injected data-onclick) are refused for a guest', async () => {
  reset({ ...ROW, role: 'guest' });
  for (const name of ['openReportEvidenceUpload', 'openReportEvidenceCamera', 'startDocumentCamera', 'docPickMethod', 'docHandleFile', 'docStartManualCheck', 'docGoStep']) {
    assert.equal(typeof ACTIONS[name], 'function', name);
  }
  await ACTIONS.openReportEvidenceCamera();
  await ACTIONS.startDocumentCamera();
  await ACTIONS.docHandleFile(png());
  await ACTIONS.docPickMethod('upload');
  assert.equal(dialogs.length, 1);
  assert.equal(cameraRequests + fileReads, 0);
  assert.equal(state.view, 'home');
  assert.equal(docState.step, 'landing');
});

test('an unresolved session never authorizes: nothing runs until the answer, then a guest is refused', async () => {
  reset({ ...ROW, role: 'guest' }, { hold: true });
  const pending = [startDocumentCamera(), openReportEvidenceCamera(), docHandleFile(png())];
  await new Promise((r) => setTimeout(r, 10));
  assert.equal(dialogs.length, 0, 'no decision before the answer');
  assert.equal(cameraRequests + fileReads, 0);
  assert.equal(state.view, 'home');
  release();
  await Promise.all(pending);
  assert.equal(dialogs.length, 1);
  assert.equal(cameraRequests + fileReads, 0);
  assert.equal(state.view, 'home');
  assert.equal(docState.step, 'landing');
});

for (const role of ['user', 'admin']) {
  test(`${role}: unchanged. Evidence screens, camera, file and manual check work (session loaded)`, async () => {
    reset({ ...ROW, role });
    await loadSessionUser();
    assert.equal(isAccountSession(), true);
    openReportEvidenceUpload();
    assert.equal(state.view, 'verify-document'); assert.equal(docState.step, 'autotype'); assert.equal(docState.method, 'upload');
    docPickAutoType('cnic');
    assert.equal(docState.step, 'upload');
    docHandleFile(png());
    assert.equal(fileReads, 1, 'file reader used');
    state.view = 'home'; resetDocState();
    openReportEvidenceCamera();
    assert.equal(docState.step, 'camera');
    startDocumentCamera();
    assert.equal(cameraRequests, 1, 'camera permission requested after authorization');
    state.view = 'home'; resetDocState();
    docPickMethod('manual');
    assert.equal(docState.step, 'type');
    docPickType('CNIC');
    assert.equal(docState.step, 'manual');
    assert.equal(dialogs.length, 0);
  });

  test(`${role}: session not loaded yet -> the action waits for the answer, then runs once`, async () => {
    reset({ ...ROW, role }, { hold: true });
    const p = startDocumentCamera();
    await new Promise((r) => setTimeout(r, 10));
    assert.equal(cameraRequests, 0, 'no camera request before the answer');
    release();
    await p;
    assert.equal(cameraRequests, 1);
    assert.equal(dialogs.length, 0);
  });
}

test('every function that opens the camera or a file or starts verification carries the check (source guard)', () => {
  const read = (p) => fs.readFileSync(new URL(`../../frontend/js/features/verifyDocument/${p}`, import.meta.url), 'utf8');
  const flow = read('flow.js'), camera = read('camera.js');
  const need = (src, names) => { for (const n of names) assert.match(src, new RegExp(`export (async )?function ${n}\\([^)]*\\)\\s*\\{ if\\(!isAccountSession\\(\\)\\) return gateThen\\(`), `${n} must start with the account check`); };
  need(flow, ['openVerifyDocument', 'openReportEvidenceUpload', 'openReportEvidenceCamera', 'docGoStep', 'docPickMethod', 'docPickAutoType', 'docPickType', 'docHandleFile', 'docStartSample', 'docStartManualCheck', 'startAutomaticVerification']);
  need(camera, ['startDocumentCamera', 'switchDocumentCamera', 'captureDocumentFrame', 'docHandleCameraCapture', 'useCapturedDocument']);
});
