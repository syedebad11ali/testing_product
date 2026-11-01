/* privacy-page.js — consent toggles, "Forget me", signed-in devices, delete account. */
import { clearBrowserState, readConsent, writeConsent } from './core/cookies.js';
import { fetchJson } from './services/http.js';
import { deleteAccount, forgetDevice, listDevices, logoutAll, revokeDevice } from './services/accountApi.js';

const $ = (sel) => document.querySelector(sel);
const say = (el, text) => { el.textContent = text; };

function syncChoices() {
  const c = readConsent();
  $('#c-pref').checked = Boolean(c && c.preferences);
  $('#c-analytics').checked = Boolean(c && c.analytics);
}

async function renderDevices() {
  const list = $('#devices');
  list.replaceChildren();
  const devices = await listDevices();
  $('#devices-empty').hidden = devices.length > 0;
  for (const d of devices) {
    const li = document.createElement('li');
    const label = document.createElement('span');
    label.textContent = `${d.label}${d.current ? ' (this device)' : ''} · last used ${new Date(d.last_used_at * 1000).toLocaleDateString()}`;
    const btn = document.createElement('button');
    btn.type = 'button'; btn.className = 'btn small'; btn.textContent = 'Remove';
    btn.setAttribute('aria-label', `Remove ${d.label}`);
    btn.addEventListener('click', async () => { btn.disabled = true; await revokeDevice(d.id); renderDevices(); });
    li.append(label, btn);
    list.appendChild(li);
  }
}

function init() {
  syncChoices();
  document.addEventListener('kpt:consent', syncChoices);

  $('#choices').addEventListener('submit', async (e) => {
    e.preventDefault();
    const before = readConsent();
    const preferences = $('#c-pref').checked, analytics = $('#c-analytics').checked;
    writeConsent({ preferences, analytics });
    document.getElementById('consentBanner')?.remove();
    if (before && before.preferences && !preferences) await forgetDevice(); // withdrawing consent also drops server-side optional state
    say($('#choices-status'), 'Saved.');
  });

  $('#forget').addEventListener('click', async () => {
    await forgetDevice();
    clearBrowserState();
    syncChoices();
    say($('#forget-status'), 'Done. Non-essential cookies were removed from this device.');
  });

  $('#logout-all').addEventListener('click', async () => {
    const { ok } = await logoutAll();
    say($('#logout-status'), ok ? 'Logged out everywhere.' : 'Could not log out. Please try again.');
    if (ok) setTimeout(() => window.location.assign('/login'), 1200);
  });

  $('#delete-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const pw = $('#del-pw').value;
    if (!pw) return say($('#delete-status'), 'Enter your password to confirm.');
    const { ok, data } = await deleteAccount(pw);
    if (ok) { clearBrowserState(); window.location.assign('/'); }
    else say($('#delete-status'), (data && data.error) || 'Could not delete the account.');
  });

  fetchJson('/api/v1/auth/me').then(({ ok, data }) => {
    // Devices, sign-out-everywhere and account deletion belong to real accounts; a guest session has none of them.
    if (ok && data && data.user && data.user.role !== 'guest') { $('#account').hidden = false; renderDevices(); }
  }).catch(() => {});
}
init();
