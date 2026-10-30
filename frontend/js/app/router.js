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
import { renderListing } from '../features/listing.js';
import { initFeatured } from '../features/featured.js';

const VIEWS = {
  home: () => renderHome(),
  detail: () => renderDetail(state.propId),
  verify: () => renderVerify(state.propId),
  report: () => renderReport(state.propId),
  verlist: () => renderSubList('verifications'),
  savedlist: () => renderSubList('saved'),
  reportslist: () => renderSubList('reports'),
  ownerverify: () => renderOwnerVerification(),
  listing: () => renderListing(state.propId),
  'verify-document': () => renderVerifyDocument(),
};

function renderFallback(message) {
  return `<div class="empty-state" role="alert"><h3>${message}</h3><p>Please go back and try again.</p><button class="btn" data-onclick="nav('home')">Back to home</button></div>`;
}

const LISTING_HASH = /^#\/(plot|house|apartment|portion|commercial|property)\/([A-Za-z0-9-]{3,40})$/;

/** Map a URL hash to a view (deep links such as /#/plot/DEMO-KPT-1648). Returns true if it matched.
 * @param {string} [hash] */
export function routeFromHash(hash = window.location.hash) {
  const m = LISTING_HASH.exec(hash || '');
  if (m) { state.view = 'listing'; state.propId = m[2].toUpperCase(); return true; }
  if (hash === '#owner-verification') { state.view = 'ownerverify'; return true; }
  if (hash === '#verify-document') { state.view = 'verify-document'; return true; }
  return false;
}

export function nav(view, propId) {
  if (docState.step === 'camera') stopDocumentCamera();
  if (view !== 'listing' && typeof history !== 'undefined' && history.replaceState && String(window.location.hash).startsWith('#/')) history.replaceState(null, '', window.location.pathname);
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
  try { initFeatured(); } catch (error) { reportError(error, 'initFeatured', { notify: false }); }   // no-op unless the home carousel is on screen
  try { renderDrawerNav(); } catch (error) { reportError(error, 'renderDrawerNav', { notify: false }); }
  if (state.view === 'ownerverify' || state.view === 'listing') loadOwnerVerificationData();
  // The full-viewport camera screens (.cam-fullscreen) cover the entire viewport themselves;
  // toggle a body class so the underlying page can't add its own scrollable overflow behind
  // the fixed overlay.
  document.body.classList.toggle('cam-active', state.view === 'verify-document' && docState.step === 'camera');
}
