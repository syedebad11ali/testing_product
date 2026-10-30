/* features/consent.js — cookie consent banner. Essential cookies are always on; Preferences and Analytics only
 * after a choice. "Reject non-essential" has the same weight as "Accept all". Static markup only (no interpolation). */
import { readConsent, writeConsent } from '../core/cookies.js';
import { forgetDevice } from '../services/accountApi.js';

const HTML = `
<div class="consent-text">
  <h2 id="consent-title">Cookies on this site</h2>
  <p>Essential cookies keep you signed in and secure, and always run. With your permission we also use
  <strong>Preferences</strong> cookies to remember your theme, filters, chat and “Remember me”.
  <strong>Analytics</strong> cookies are off: this site does not use any yet. <a href="/privacy">Privacy &amp; cookies</a></p>
  <div class="consent-details" hidden>
    <label class="consent-row"><input type="checkbox" checked disabled> <span><strong>Essential</strong> Sign-in session, security token, your choice here</span></label>
    <label class="consent-row"><input type="checkbox" id="consent-pref"> <span><strong>Preferences</strong> Theme, filters, recently viewed, chat continuity, Remember me</span></label>
    <label class="consent-row"><input type="checkbox" id="consent-analytics"> <span><strong>Analytics</strong> Reserved. Nothing is collected today</span></label>
  </div>
</div>
<div class="consent-actions">
  <button type="button" class="consent-btn" data-choice="reject">Reject non-essential</button>
  <button type="button" class="consent-btn" data-choice="all">Accept all</button>
  <button type="button" class="consent-btn consent-link" data-choice="customise" aria-expanded="false">Customise</button>
</div>`;

/** Shows the banner when there is no valid, current choice. Safe to call more than once. */
export function initConsent() {
  if (typeof document === 'undefined' || readConsent() || document.getElementById('consentBanner')) return;
  const root = document.createElement('section');
  root.id = 'consentBanner';
  root.className = 'consent-banner';
  root.setAttribute('role', 'region');
  root.setAttribute('aria-labelledby', 'consent-title');
  root.innerHTML = HTML;
  document.body.appendChild(root);
  // Keep the page reachable while the banner is open: reserve its height at the bottom of the page (it follows the
  // banner when the text wraps, the viewport turns, or "Customise" expands it) and release it on any choice.
  document.body.classList.add('has-consent');
  const reserve = () => document.documentElement.style.setProperty('--consent-h', `${root.offsetHeight + 24}px`);
  reserve();
  const watcher = typeof ResizeObserver === 'function' ? new ResizeObserver(reserve) : null;
  if (watcher) watcher.observe(root); else window.addEventListener('resize', reserve);
  const details = root.querySelector('.consent-details');
  const custom = root.querySelector('[data-choice="customise"]');

  const decide = (preferences, analytics) => {
    const hadPreferences = false; // the banner only appears when no choice exists, so nothing to withdraw
    writeConsent({ preferences, analytics });
    if (hadPreferences && !preferences) forgetDevice();
    if (watcher) watcher.disconnect(); else window.removeEventListener('resize', reserve);
    document.body.classList.remove('has-consent');
    document.documentElement.style.removeProperty('--consent-h');
    root.remove();
    document.dispatchEvent(new CustomEvent('kpt:consent', { detail: { preferences, analytics } }));
  };
  root.addEventListener('click', (event) => {
    const choice = event.target && event.target.getAttribute && event.target.getAttribute('data-choice');
    if (choice === 'reject') decide(false, false);
    else if (choice === 'all') decide(true, true);
    else if (choice === 'customise') {
      if (details.hidden) {
        details.hidden = false; custom.textContent = 'Save my choices'; custom.setAttribute('aria-expanded', 'true');
      } else decide(root.querySelector('#consent-pref').checked, root.querySelector('#consent-analytics').checked);
    }
  });
}
