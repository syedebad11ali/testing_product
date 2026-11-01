/* Top-nav account state: "Log in" when signed out, name + Admin/Log out when signed in.
 * Display only: the server decides what the user may actually do. */
import { fetchJson } from '../services/http.js';
import { clearFavorites } from './favorites.js';
import { clearHomeFilters } from './homePrefs.js';
import { clearDocHistory } from '../state/store.js';

export async function initAuthNav() {
  const slot = document.getElementById('authLink');
  const mobileSlot = document.getElementById('mobileAuthLink');
  if (!slot && !mobileSlot) return;
  try {
    const { ok, data } = await fetchJson('/api/v1/auth/me');
    const user = ok && data ? data.user : null;
    const accountLabel = document.getElementById('mobileAccountName');
    if (accountLabel) accountLabel.textContent = user ? (user.role === 'guest' ? 'Guest' : user.name.split(' ')[0]) : 'Account';
    if (!user) return;  // keeps the default "Log in" link
    for (const target of [slot, mobileSlot]) if (target) populateAuthSlot(target, user);
  } catch (_) { /* offline or API down: leave the default link */ }
}

function populateAuthSlot(slot, user) {
  slot.replaceChildren();
  if (user.role === 'guest') {
    const badge = document.createElement('span');
    badge.className = 'auth-guest'; badge.textContent = 'Guest'; badge.title = 'Browsing as a guest: messaging, listings and checks need an account';
    slot.appendChild(badge);
    for (const [label, href, cls] of [['Log in', '/login', 'auth-pill'], ['Sign up', '/signup', 'auth-pill solid']]) {
      const a = document.createElement('a'); a.className = cls; a.href = href; a.textContent = label; slot.appendChild(a);
    }
    const exit = document.createElement('button');
    exit.type = 'button'; exit.className = 'auth-logout'; exit.textContent = 'Exit'; exit.setAttribute('aria-label', 'Exit guest mode'); exit.title = 'Exit guest mode';
    exit.addEventListener('click', async () => { await fetchJson('/api/v1/auth/logout', { method: 'POST', body: {} }); clearFavorites(); clearHomeFilters(); clearDocHistory(); location.assign('/login'); });
    slot.appendChild(exit);
    return;
  }
  const name = document.createElement('span');
  name.className = 'auth-name'; name.textContent = user.name.split(' ')[0];
  slot.appendChild(name);
  if (user.role === 'admin') {
    const admin = document.createElement('a'); admin.href = '/admin'; admin.textContent = 'Admin'; slot.appendChild(admin);
  }
  const out = document.createElement('button');
  out.type = 'button'; out.className = 'auth-logout'; out.textContent = 'Log out';
  out.addEventListener('click', async () => { await fetchJson('/api/v1/auth/logout', { method: 'POST', body: {} }); clearFavorites(); clearHomeFilters(); clearDocHistory(); location.assign('/login'); });
  slot.appendChild(out);
}
