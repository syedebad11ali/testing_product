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
import { showLoginRequired } from '../features/loginPrompt.js';
import { guestBlockedView, isAccountUser, loadSessionUser } from '../services/sessionUser.js';

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

/* Account-only views (sessionUser.GUEST_BLOCKED_VIEWS): a guest or signed-out visitor gets the shared "Login required" dialog instead.
 * Display only; the server still refuses every account API call. */
const FEATURE_NAMES = {
  verify: 'Property verification', report: 'Report a property', verlist: 'My verifications', savedlist: 'Saved properties',
  reportslist: 'My reports', ownerverify: 'Owner verification', 'verify-document': 'Document verification',
};
const VIEW_HASH = { ownerverify: '#owner-verification', 'verify-document': '#verify-document' };   // views that have a deep-link hash

let routeSeq = 0;   // the latest navigation wins: a slower, older permission check must not apply its view or open a dialog

/** Resolves the session (awaiting the one GET /auth/me), then decides. Only a LOADED account user or admin is allowed: guest,
 * signed-out and an unreachable/unknown session all get the dialog (`next` = the path to return to after login). Never touches the session. */
async function allowAccountView(view, next) {
  let user = null;
  try { user = await loadSessionUser(); } catch { user = null; }
  if (isAccountUser(user)) return true;
  showLoginRequired({ feature: FEATURE_NAMES[view], next });   // an already-open dialog is reused, so there is never a second one
  return false;
}

const hashPath = (hash) => `${window.location.pathname || '/'}${window.location.search || ''}${hash}`;

/** Map a URL hash to a view (deep links such as /#/plot/DEMO-KPT-1648). Resolves to true if a view was applied.
 * Open views are applied synchronously (before the first await); account-only views wait for the session check.
 * @param {string} [hash]
 * @returns {Promise<boolean>} */
export async function routeFromHash(hash = window.location.hash) {
  const seq = ++routeSeq;
  const m = LISTING_HASH.exec(hash || '');
  if (m) { state.view = 'listing'; state.propId = m[2].toUpperCase(); return true; }
  const view = hash === '#owner-verification' ? 'ownerverify' : hash === '#verify-document' ? 'verify-document' : null;
  if (!view) return false;
  if (guestBlockedView(view)) {
    const allowed = await allowAccountView(view, hashPath(hash));
    if (seq !== routeSeq) return false;
    if (!allowed) {
      // drop the refused hash so clicking the same link again fires hashchange (and a refresh is a fresh decision)
      if (window.location.hash === hash && typeof history !== 'undefined' && history.replaceState) history.replaceState(null, '', `${window.location.pathname}${window.location.search || ''}`);
      return false;
    }
  }
  state.view = view;
  return true;
}

function go(view, propId) {
  if (docState.step === 'camera') stopDocumentCamera();
  if (view !== 'listing' && typeof history !== 'undefined' && history.replaceState && String(window.location.hash).startsWith('#/')) history.replaceState(null, '', window.location.pathname);
  state.view = view;
  state.propId = propId || null;
  window.scrollTo(0, 0);
  render();
}

/** Go to a view. Open views switch immediately (unchanged); account-only views first await the session check and, for a guest or
 * signed-out visitor, show the login dialog and stay on the current screen. @returns {Promise<boolean>} true if navigation happened */
export function nav(view, propId) {
  const seq = ++routeSeq;
  if (!guestBlockedView(view)) { go(view, propId); return Promise.resolve(true); }
  return allowAccountView(view, VIEW_HASH[view] ? hashPath(VIEW_HASH[view]) : undefined).then((allowed) => {
    if (!allowed || seq !== routeSeq) return false;
    go(view, propId);
    return true;
  });
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
