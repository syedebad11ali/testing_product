/* Top-nav account state: "Log in" when signed out, name + Admin/Log out when signed in.
 * Display only: the server decides what the user may actually do. */
import { fetchJson } from '../services/http.js';

export async function initAuthNav() {
  const slot = document.getElementById('authLink');
  if (!slot) return;
  try {
    const { ok, data } = await fetchJson('/api/v1/auth/me');
    const user = ok && data ? data.user : null;
    if (!user) return;  // keeps the default "Log in" link
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
      exit.addEventListener('click', async () => { await fetchJson('/api/v1/auth/logout', { method: 'POST', body: {} }); location.assign('/login'); });
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
    out.addEventListener('click', async () => { await fetchJson('/api/v1/auth/logout', { method: 'POST', body: {} }); location.assign('/login'); });
    slot.appendChild(out);
  } catch (_) { /* offline or API down: leave the default link */ }
}
