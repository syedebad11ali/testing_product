/* Login / sign-up / forced-password-change page (design: design-reference/login).
 * All authentication decisions are made by the server; this file collects input, validates it for
 * friendly inline messages, calls the API and follows the redirect the server returns.
 * The server re-validates everything (min 10 characters, common-password check). */
import { fetchJson } from './services/http.js';
import { syncPrefsAfterLogin } from './services/accountApi.js';

const $ = (sel, root = document) => root.querySelector(sel);
const API = '/api/v1/auth';
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
export const MIN_PASSWORD = 10; // mirrors backend/security/passwords.py; the server is authoritative

/** Only same-site absolute paths are followed (blocks open redirects such as //evil.example or /\evil). */
export function safeRedirect(target) {
  return typeof target === 'string' && /^\/(?![/\\])/.test(target) ? target : '/';
}

/** 0..4 strength score used for the hint bar (the server enforces the real policy). */
export function strength(pw) {
  let score = 0;
  if (pw.length >= 10) score++;
  if (pw.length >= 14) score++;
  if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) score++;
  if (/\d/.test(pw) && /[^A-Za-z0-9]/.test(pw)) score++;
  return pw.length < MIN_PASSWORD ? Math.min(score, 1) : score; // below the minimum it can never look "Okay"
}

/** Validation for the three forms. Returns { field: message } (empty object = valid). */
export function validate(kind, v) {
  const e = {};
  if (kind === 'login') {
    if (!v.identifier.trim()) e.identifier = 'Username or email is required.';
    if (!v.password) e.password = 'Password is required.';
  } else if (kind === 'signup') {
    if (!v.name.trim()) e.name = 'Full name is required.';
    if (!v.email.trim()) e.email = 'Email is required.';
    else if (!EMAIL_RE.test(v.email.trim())) e.email = 'Enter a valid email address.';
    if (!v.password) e.password = 'Password is required.';
    else if (v.password.length < MIN_PASSWORD) e.password = `Use at least ${MIN_PASSWORD} characters.`;
    if (v.confirm !== v.password) e.confirm = 'Passwords do not match.';
  } else if (kind === 'forgot') {
    if (!v.email.trim()) e.email = 'Email is required.';
    else if (!EMAIL_RE.test(v.email.trim())) e.email = 'Enter a valid email address.';
  } else if (kind === 'reset') {
    if (!v.new_password) e.new_password = 'New password is required.';
    else if (v.new_password.length < MIN_PASSWORD) e.new_password = `Use at least ${MIN_PASSWORD} characters.`;
    if (v.confirm !== v.new_password) e.confirm = 'Passwords do not match.';
  } else if (kind === 'change') {
    if (!v.current_password) e.current_password = 'Current password is required.';
    if (!v.new_password) e.new_password = 'New password is required.';
    else if (v.new_password.length < MIN_PASSWORD) e.new_password = `Use at least ${MIN_PASSWORD} characters.`;
  }
  return e;
}

/** True when the key event reports Caps Lock as active (feature-detected; some synthetic events lack the method). */
export function isCapsLockOn(event) {
  return Boolean(event && typeof event.getModifierState === 'function' && event.getModifierState('CapsLock'));
}

/** Inline message when a confirmation field is filled in but differs from the password; '' when fine or still empty. */
export function confirmMismatch(password, confirm) {
  return confirm && confirm !== password ? 'Passwords do not match.' : '';
}

/** Where to go after a successful sign-in: the server's choice, except a normal "/" may honour ?next=. */
/** A guest may only land on the public browsing pages; anything else (messages, admin, ...) goes to the home page. */
export function guestDestination(next) {
  const target = safeRedirect(next);
  return target === '/listings' || target.startsWith('/listings?') ? target : '/';
}

/** Message for a failed "Continue as Guest" request, from the server's own error shape ({error, code}). */
export function guestErrorMessage(status, data) {
  if (data && data.code === 'guest_limit') return data.error || 'Too many guest sessions from this network. Please try again later or create an account.';
  if (status === 429) return 'Too many attempts. Please wait a moment and try again.';
  return (data && data.error) || 'Could not start a guest session. Please try again.';
}

export function afterLogin(serverRedirect, next) {
  const target = safeRedirect(serverRedirect);
  return target === '/' && next ? safeRedirect(next) : target;
}

function fieldWrap(input) { return input.closest('.field'); }

function setFieldError(input, message) {
  const wrap = fieldWrap(input);
  const box = $('.input', wrap);
  let err = $('.err', wrap);
  box.classList.toggle('has-error', !!message);
  input.setAttribute('aria-invalid', message ? 'true' : 'false');
  if (!message) { if (err) err.remove(); input.removeAttribute('aria-describedby'); return; }
  if (!err) { err = document.createElement('p'); err.className = 'err'; err.setAttribute('role', 'alert'); wrap.append(err); }
  err.id = `${input.id}-err`;
  err.textContent = message;
  input.setAttribute('aria-describedby', err.id);
}

function showErrors(form, errors) {
  let first = null;
  for (const input of form.querySelectorAll('input:not([type=checkbox])')) {
    setFieldError(input, errors[input.name] || '');
    if (errors[input.name] && !first) first = input;
  }
  if (first) first.focus();
  return !first;
}

function setBusy(form, busy, label) {
  const btn = $('button[type=submit]', form);
  btn.disabled = busy; // no double submits
  $('.spin', btn).hidden = !busy;
  $('[data-label]', btn).textContent = busy ? 'Please wait…' : label;
  form.setAttribute('aria-busy', String(busy));
  // From the login design reference: while a request is in flight the Google button cannot start a second sign-in.
  for (const g of form.querySelectorAll('.gbox')) g.classList.toggle('busy', busy);
  for (const g of form.querySelectorAll('button[data-google]')) g.disabled = busy;
}

const banner = (form, msg) => { $('[data-banner]', form).textContent = msg || ''; };
const values = (form) => Object.fromEntries([...form.elements].filter((el) => el.name).map((el) => [el.name, el.value]));

async function post(form, path, payload, label, onOk) {
  banner(form, '');
  setBusy(form, true, label);
  try {
    const { ok, data } = await fetchJson(`${API}/${path}`, { method: 'POST', body: payload });
    if (data && data.redirect && (ok || data.redirect === '/nice-try')) return onOk(data);
    banner(form, (data && data.error) || 'Something went wrong. Please try again.');
  } catch (e) {
    banner(form, e.message || 'Could not reach the server.');
  } finally { setBusy(form, false, label); }
}

/** Loads Google Identity Services and swaps the placeholder buttons for Google's official one. */
async function setupGoogle(banner, onDone, wantsRemember = () => false) {
  let cfg;
  try { cfg = (await fetchJson(`${API}/google/config`)).data; } catch { return; }
  if (!cfg || !cfg.configured) return;
  try { await loadScript('https://accounts.google.com/gsi/client'); } catch { return; }
  const gsi = window.google && window.google.accounts && window.google.accounts.id;
  if (!gsi) return;
  gsi.initialize({
    client_id: cfg.client_id, nonce: cfg.nonce, use_fedcm_for_button: true, auto_select: false,
    callback: async (res) => {
      const form = document.querySelector('form:not([hidden])');
      if (!res || !res.credential) return banner(form, 'Google sign-in was cancelled.');
      try {
        const { ok, data } = await fetchJson(`${API}/google`, { method: 'POST', body: { credential: res.credential, remember: wantsRemember() } });
        if (ok && data && data.redirect) return onDone(data);
        banner(form, (data && data.error) || 'Google sign-in failed. Please try again.');
        window.location.reload(); // the nonce was consumed; a reload fetches a fresh one
      } catch (e) { banner(form, e.message || 'Could not reach the server.'); }
    },
  });
  for (const btn of document.querySelectorAll('[data-google]')) {
    const box = document.createElement('div');
    box.className = 'gbox';
    btn.before(box);
    gsi.renderButton(box, { theme: 'outline', size: 'large', shape: 'pill', text: 'continue_with', logo_alignment: 'center', width: 400 });
    btn.hidden = true;
  }
}

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const el = document.createElement('script');
    el.src = src; el.async = true; el.onload = resolve; el.onerror = reject;
    document.head.append(el);
  });
}

function init() {
  const params = new URLSearchParams(location.search);
  const forms = { login: $('#form-login'), signup: $('#form-signup'), forgot: $('#form-forgot'), reset: $('#form-reset'), change: $('#form-change') };
  const labels = { login: 'Login', signup: 'Create account', forgot: 'Send reset link', reset: 'Set new password', change: 'Change password' };
  const navBtn = { login: $('#nav-login'), signup: $('#nav-signup') };

  function show(name, focus = true) {
    for (const [k, f] of Object.entries(forms)) f.hidden = k !== name;
    for (const [k, b] of Object.entries(navBtn)) { if (k === name) b.setAttribute('aria-current', 'true'); else b.removeAttribute('aria-current'); }
    for (const f of Object.values(forms)) { banner(f, ''); $('[data-banner]', f).classList.remove('ok'); showErrors(f, {}); }
    if (name === 'login' || name === 'signup') history.replaceState(null, '', (name === 'signup' ? '/signup' : '/login') + (params.get('next') ? `?next=${encodeURIComponent(params.get('next'))}` : ''));
    if (focus) $('input', forms[name]).focus();
  }

  navBtn.login.addEventListener('click', () => show('login'));
  navBtn.signup.addEventListener('click', () => show('signup'));
  for (const b of document.querySelectorAll('[data-switch]')) b.addEventListener('click', () => show(b.dataset.switch));

  for (const btn of document.querySelectorAll('[data-eye]')) {
    btn.addEventListener('click', () => {
      const input = btn.previousElementSibling;
      const reveal = input.type === 'password';
      input.type = reveal ? 'text' : 'password';
      btn.setAttribute('aria-pressed', String(reveal));
      btn.setAttribute('aria-label', reveal ? 'Hide password' : 'Show password');
      $('.slash', btn).hidden = !reveal;
    });
  }

  // Google sign-in: the server decides whether it is configured (GOOGLE_CLIENT_ID) and issues a single-use
  // nonce. Until then the button says so and never fakes a sign-in. Verification happens on the server.
  const notConfigured = (e) => banner(e.currentTarget.closest('form'), 'Google sign-in is not configured yet. Use your email and password for now.');
  for (const g of document.querySelectorAll('[data-google]')) g.addEventListener('click', notConfigured);
  setupGoogle(banner, (data) => done(data), () => Boolean(document.getElementById('login-remember') && document.getElementById('login-remember').checked));

  // Continue as Guest: a restricted server-side guest session (no credentials). One request at a time.
  const guestBtn = $('#guest-btn');
  if (guestBtn) {
    let starting = false;
    const lock = (busy) => {
      starting = busy;
      guestBtn.disabled = busy;
      $('.spin', guestBtn).hidden = !busy;
      $('[data-label]', guestBtn).textContent = busy ? 'Please wait…' : 'Continue as Guest';
      for (const el of document.querySelectorAll('button[type=submit], button[data-google]')) el.disabled = busy;
    };
    guestBtn.addEventListener('click', async () => {
      if (starting) return;
      lock(true); banner(forms.login, '');
      try {
        const { ok, status, data } = await fetchJson(`${API}/guest`, { method: 'POST', body: {} });
        // Trust only a real guest session: never treat any other answer as being signed in.
        if (ok && data && data.user && data.user.role === 'guest') { location.assign(guestDestination(params.get('next'))); return; }
        banner(forms.login, guestErrorMessage(status, data));
      } catch (_) {
        banner(forms.login, 'Could not reach the server. Check your connection and try again.');
      }
      lock(false);
    });
  }

  // Clear a field's error as soon as it is edited.
  for (const f of Object.values(forms)) f.addEventListener('input', (e) => { if (e.target.name) setFieldError(e.target, ''); });

  // Caps Lock hint under every password field (one polite live region per field; empty = hidden by CSS).
  for (const input of document.querySelectorAll('input[type=password]')) {
    const note = document.createElement('p');
    note.className = 'hint caps';
    note.setAttribute('role', 'status');
    fieldWrap(input).append(note);
    const update = (e) => { note.textContent = isCapsLockOn(e) ? 'Caps Lock is on.' : ''; };
    input.addEventListener('keydown', update);
    input.addEventListener('keyup', update);
    input.addEventListener('blur', () => { note.textContent = ''; });
  }

  // Pressing a submit button must not blur the field that has focus: the blur check below can insert an error line under that
  // field, which pushes the button down between mouse-down and mouse-up so the click is lost and the form never submits (users
  // had to click twice). Keyboard users are unaffected (Tab/Enter still move focus normally); validation runs on submit.
  for (const f of Object.values(forms)) {
    const submit = f && f.querySelector('button[type=submit]');
    if (submit) submit.addEventListener('mousedown', (event) => event.preventDefault());
  }

  // Tell people the confirmation differs as soon as they leave the field, not only on submit.
  for (const [confirmId, passwordId] of [['su-confirm', 'su-pw'], ['rs-confirm', 'rs-new']]) {
    const confirm = document.getElementById(confirmId); const password = document.getElementById(passwordId);
    if (confirm && password) confirm.addEventListener('blur', () => setFieldError(confirm, confirmMismatch(password.value, confirm.value)));
  }

  const pw = $('#su-pw');
  pw.addEventListener('input', () => {
    const s = strength(pw.value);
    $('#pw-meter').style.width = `${s * 25}%`;
    $('#pw-hint').textContent = pw.value
      ? `${['Too weak', 'Weak', 'Okay', 'Good', 'Strong'][s]}${pw.value.length < MIN_PASSWORD ? ` · at least ${MIN_PASSWORD} characters` : ''}`
      : 'At least 10 characters. Very common passwords are rejected.';
  });

  const next = params.get('next');
  const done = async (data) => {
    if (data.redirect !== '/nice-try') await syncPrefsAfterLogin();   // merge cookie prefs into the account
    if (data.remember_note) {                                       // e.g. Preferences cookies not allowed
      banner(document.querySelector('form:not([hidden])'), data.remember_note);
      await new Promise((resolve) => setTimeout(resolve, 3000));
    }
    window.location.assign(afterLogin(data.redirect, next));
  };

  forms.login.addEventListener('submit', (e) => {
    e.preventDefault();
    const v = values(forms.login);
    if (!showErrors(forms.login, validate('login', v))) return;
    post(forms.login, 'login', { identifier: v.identifier.trim(), password: v.password, remember: $('#login-remember').checked }, labels.login, done);
  });
  forms.signup.addEventListener('submit', (e) => {
    e.preventDefault();
    const v = values(forms.signup);
    if (!showErrors(forms.signup, validate('signup', v))) return;
    post(forms.signup, 'signup', { name: v.name.trim(), email: v.email.trim(), password: v.password }, labels.signup, done);
  });
  forms.forgot.addEventListener('submit', async (e) => {
    e.preventDefault();
    const v = values(forms.forgot);
    if (!showErrors(forms.forgot, validate('forgot', v))) return;
    banner(forms.forgot, ''); setBusy(forms.forgot, true, labels.forgot);
    try {
      const { ok, data } = await fetchJson(`${API}/forgot`, { method: 'POST', body: { email: v.email.trim() } });
      const msg = $('[data-banner]', forms.forgot);
      if (ok) { msg.classList.add('ok'); msg.setAttribute('role', 'status'); msg.textContent = (data && data.message) || 'If that email has an account, a reset link is on its way.'; }
      else banner(forms.forgot, (data && data.error) || 'Could not send the link. Please try again.');
    } catch (err) { banner(forms.forgot, err.message); } finally { setBusy(forms.forgot, false, labels.forgot); }
  });
  const resetToken = params.get('reset');
  forms.reset.addEventListener('submit', async (e) => {
    e.preventDefault();
    const v = values(forms.reset);
    if (!showErrors(forms.reset, validate('reset', v))) return;
    banner(forms.reset, ''); setBusy(forms.reset, true, labels.reset);
    try {
      const { ok, data } = await fetchJson(`${API}/reset`, { method: 'POST', body: { token: resetToken, new_password: v.new_password } });
      if (ok) { show('login'); const b = $('[data-banner]', forms.login); b.classList.add('ok'); b.textContent = 'Password updated. Log in with your new password.'; }
      else banner(forms.reset, (data && data.error) || 'Could not reset the password.');
    } catch (err) { banner(forms.reset, err.message); } finally { setBusy(forms.reset, false, labels.reset); }
  });
  forms.change.addEventListener('submit', async (e) => {
    e.preventDefault();
    const v = values(forms.change);
    if (!showErrors(forms.change, validate('change', v))) return;
    banner(forms.change, ''); setBusy(forms.change, true, labels.change);
    try {
      const { ok, data } = await fetchJson(`${API}/change-password`, { method: 'POST', body: { current_password: v.current_password, new_password: v.new_password } });
      if (ok) window.location.assign('/admin'); else banner(forms.change, (data && data.error) || 'Could not change the password.');
    } catch (err) { banner(forms.change, err.message); } finally { setBusy(forms.change, false, labels.change); }
  });

  // Tell the user honestly when emailed resets are not set up on this deployment.
  fetchJson(`${API}/features`).then(({ data }) => {
    if (data && data.password_reset === false) $('#forgot-note').textContent = 'Password reset by email is not set up on this site yet. Please contact the administrator.';
  }).catch(() => {});

  if (resetToken) {
    history.replaceState(null, '', '/login'); // keep the token out of the address bar, history and Referer
    show('reset', false); return;
  }
  if (params.get('change') === '1') { show('change', false); return; }
  show(location.pathname === '/signup' ? 'signup' : 'login', false);

  // Already signed in? Say so instead of showing the form again.
  fetchJson(`${API}/me`).then(({ ok, data }) => {
    if (!ok || !data || !data.user) return;
    if (data.user.role === 'guest') { banner(forms.login, 'You are browsing as a guest. Log in or create an account to use messaging, listings and checks.'); return; }
    for (const f of Object.values(forms)) f.hidden = true;
    $('#welcome-name').textContent = data.user.name || data.user.email || 'your account';
    $('#welcome-continue').href = afterLogin(data.user.role === 'admin' ? '/admin' : '/', next);
    $('#welcome').hidden = false;
  }).catch(() => {});
}

if (typeof document !== 'undefined' && document.getElementById('form-login')) init();
