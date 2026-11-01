/* Developer Login page. The server decides everything: it answers {redirect: "/admin"} (session started) for an
 * authorised administrator and {redirect: "/nice-try"} (no session) for any other attempt. Only same-site paths are followed. */
import { fetchJson } from './services/http.js';

const form = document.querySelector('#form-dev');
const banner = form.querySelector('[data-banner]');
const btn = form.querySelector('button[type=submit]');
const label = btn.querySelector('[data-label]').textContent;
const spin = btn.querySelector('.spin');

function safeRedirect(target) {
  return typeof target === 'string' && /^\/(?![/\\])/.test(target) ? target : '/';
}

function busy(on) {
  btn.disabled = on;
  spin.hidden = !on;
  btn.querySelector('[data-label]').textContent = on ? 'Please wait…' : label;
  form.setAttribute('aria-busy', String(on));
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const identifier = form.elements.identifier.value.trim();
  const password = form.elements.password.value;
  banner.textContent = '';
  if (!identifier || !password) { banner.textContent = 'Enter the administrator username and password.'; return; }
  busy(true);
  try {
    const { ok, data } = await fetchJson('/api/v1/auth/developer-login', { method: 'POST', body: { identifier, password } });
    if (data && data.redirect && (ok || data.redirect === '/nice-try')) { window.location.assign(safeRedirect(data.redirect)); return; }
    banner.textContent = (data && data.error) || 'Something went wrong. Please try again.';
  } catch (err) {
    banner.textContent = err.message || 'Could not reach the server.';
  }
  busy(false);
});
