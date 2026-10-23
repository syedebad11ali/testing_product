/* View routing + the render loop. `state.view` selects the screen; every screen is a
 * function returning an HTML string. Rendering is wrapped in an error boundary so a bug in
 * one screen shows a recovery card instead of a blank page. */
import { docState, state } from '../state/store.js';
import { reportError } from '../core/errors.js';
import { renderHome } from '../features/home.js';
import { renderDetail, renderReport, renderSubList, renderVerify } from '../features/property.js';
import { loadOwnerVerificationData, renderOwnerVerification } from '../features/ownerVerification.js';
import { renderVerifyDocument } from '../features/verifyDocument/views.js';
import { stopDocumentCamera } from '../features/verifyDocument/camera.js';
import { renderDrawerNav } from '../features/drawer.js';

const VIEWS = {
  home: () => renderHome(),
  detail: () => renderDetail(state.propId),
  verify: () => renderVerify(state.propId),
  report: () => renderReport(state.propId),
  verlist: () => renderSubList('verifications'),
  savedlist: () => renderSubList('saved'),
  reportslist: () => renderSubList('reports'),
  ownerverify: () => renderOwnerVerification(),
  'verify-document': () => renderVerifyDocument(),
};

function renderFallback(message) {
  return `<div class="empty-state" role="alert"><h3>${message}</h3><p>Please go back and try again.</p><button class="btn" onclick="nav('home')">Back to home</button></div>`;
}

export function nav(view, propId) {
  if (docState.step === 'camera') stopDocumentCamera();
  state.view = view;
  state.propId = propId || null;
  window.scrollTo(0, 0);
  render();
}

export function render() {
  const root = document.getElementById('app');
  const view = VIEWS[state.view];
  try {
    if (!view) {
      reportError(new Error(`Unknown view "${state.view}"`), 'render', { notify: false });
      state.view = 'home';
    }
    root.innerHTML = (VIEWS[state.view])();
  } catch (error) {
    reportError(error, `render:${state.view}`);
    root.innerHTML = renderFallback('This page could not be displayed.');
  }
  try { renderDrawerNav(); } catch (error) { reportError(error, 'renderDrawerNav', { notify: false }); }
  if (state.view === 'ownerverify') loadOwnerVerificationData();
  // The full-viewport camera screens (.cam-fullscreen) cover the entire viewport themselves;
  // toggle a body class so the underlying page can't add its own scrollable overflow behind
  // the fixed overlay.
  document.body.classList.toggle('cam-active', state.view === 'verify-document' && docState.step === 'camera');
}
