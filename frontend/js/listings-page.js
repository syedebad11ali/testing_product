/* Seller listings page: create, my listings, browse, detail with "Chat with seller".
 * Every user-supplied string is written with textContent. The server decides who may create (signed in, not banned). */
import { fetchJson } from './services/http.js';
import { chatWithSeller } from './features/sellerChat.js';

const $ = (s) => document.querySelector(s);
const say = (t) => { $('#msg').textContent = t || ''; };
const REF = /^[A-Za-z0-9_-]{1,40}$/;
let page = 1;
let creating = false;

function row(l, withStatus) {
  const li = document.createElement('li'); li.className = 'ls-item';
  const text = document.createElement('div');
  const b = document.createElement('b'); b.textContent = l.title;
  const s = document.createElement('small'); s.textContent = `${l.area} · unverified${withStatus ? ` · ${l.status}` : ''} · ref ${l.ref}`;
  text.append(b, s);
  const open = document.createElement('button'); open.type = 'button'; open.className = 'ls-open'; open.textContent = 'View';
  open.setAttribute('aria-label', `View ${l.title}`);
  open.addEventListener('click', () => showDetail(l.ref, true));
  const actions = document.createElement('div'); actions.className = 'ls-actions';
  actions.append(open);
  if (withStatus) {
    const edit = document.createElement('button'); edit.type = 'button'; edit.className = 'ls-open'; edit.textContent = 'Edit';
    edit.setAttribute('aria-label', `Edit ${l.title}`);
    edit.addEventListener('click', () => openEditor(li, l, edit));
    const closing = l.status === 'active';
    const toggle = document.createElement('button'); toggle.type = 'button'; toggle.className = 'ls-open';
    toggle.textContent = closing ? 'Close' : 'Reopen';
    toggle.setAttribute('aria-label', `${closing ? 'Close' : 'Reopen'} ${l.title}`);
    toggle.addEventListener('click', () => changeStatus(l, closing ? 'closed' : 'active', toggle));
    actions.append(edit, toggle);
  }
  li.append(text, actions);
  return li;
}

async function changeStatus(l, status, btn) {
  btn.disabled = true; say('');
  const live = $('#mine-status'); live.textContent = status === 'closed' ? 'Closing…' : 'Reopening…';
  try {
    const { ok, data } = await fetchJson(`/api/v1/listings/${encodeURIComponent(l.ref)}/status`, { method: 'POST', body: { status } });
    if (!ok) { live.textContent = (data && data.error) || 'Could not update the listing.'; btn.disabled = false; btn.focus(); return; }
    live.textContent = status === 'closed' ? `Closed “${l.title}”. It is hidden from browse and no new chats can start.` : `Reopened “${l.title}”.`;
    await Promise.all([loadMine(), loadBrowse(true)]);
  } catch (e) { live.textContent = e.message || 'Could not reach the server.'; btn.disabled = false; btn.focus(); }
}

function openEditor(li, l, trigger) {
  if (li.querySelector('form')) return;
  const f = document.createElement('form'); f.className = 'ls-edit'; f.noValidate = true;
  const mk = (id, label, val, max) => {
    const lab = document.createElement('label'); lab.htmlFor = id; lab.textContent = label;
    const i = document.createElement('input'); i.type = 'text'; i.id = id; i.maxLength = max; i.value = val; i.autocomplete = 'off';
    return [lab, i];
  };
  const [lt, it] = mk(`e-t-${l.ref}`, 'Title', l.title, 120), [la, ia] = mk(`e-a-${l.ref}`, 'Area', l.area, 80);
  const save = document.createElement('button'); save.type = 'submit'; save.className = 'auth-btn'; save.textContent = 'Save';
  const cancel = document.createElement('button'); cancel.type = 'button'; cancel.className = 'ls-open'; cancel.textContent = 'Cancel';
  const st = document.createElement('p'); st.className = 'auth-hint'; st.setAttribute('role', 'status'); st.setAttribute('aria-live', 'polite');
  f.append(lt, it, la, ia, save, cancel, st);
  const done = () => { f.remove(); trigger.focus(); };
  cancel.addEventListener('click', done);
  f.addEventListener('keydown', (e) => { if (e.key === 'Escape') { e.preventDefault(); done(); } });
  f.addEventListener('submit', async (e) => {
    e.preventDefault();
    const title = it.value.trim(), area = ia.value.trim();
    if (title.length < 3 || title.length > 120) { st.textContent = 'Enter a title of 3 to 120 characters.'; it.focus(); return; }
    if (area.length < 2 || area.length > 80) { st.textContent = 'Enter an area of 2 to 80 characters.'; ia.focus(); return; }
    save.disabled = true; st.textContent = 'Saving…';
    try {
      const { ok, data } = await fetchJson(`/api/v1/listings/${encodeURIComponent(l.ref)}/edit`, { method: 'POST', body: { title, area } });
      if (!ok) { st.textContent = (data && data.error) || 'Could not save.'; save.disabled = false; return; }
      $('#mine-status').textContent = `Saved “${data.listing.title}”.`;
      await Promise.all([loadMine(), loadBrowse(true)]);
    } catch (err) { st.textContent = err.message || 'Could not reach the server.'; save.disabled = false; }
  });
  li.append(f); it.focus();
}

async function loadBrowse(reset) {
  if (reset) { page = 1; $('#browse').replaceChildren(); }
  const { ok, data } = await fetchJson(`/api/v1/listings?page=${page}`);
  if (!ok || !data) { say((data && data.error) || 'Could not load listings.'); return; }
  for (const l of data.listings) $('#browse').appendChild(row(l, false));
  $('#browse-empty').hidden = $('#browse').children.length > 0;
  $('#more').hidden = !data.has_more;
}

let minePage = 1;

async function loadMine(page = minePage) {
  const { ok, data } = await fetchJson(`/api/v1/listings/mine?page=${page}&per_page=10`);
  if (!ok || !data) return;
  if (data.listings.length === 0 && page > 1) return loadMine(page - 1);   // the last item on a page was removed
  minePage = data.page;
  $('#mine').replaceChildren(...data.listings.map((l) => row(l, true)));
  $('#mine-empty').hidden = data.total > 0;
  const pages = Math.max(1, Math.ceil(data.total / data.per_page));
  $('#mine-pager').hidden = pages <= 1;
  $('#mine-page').textContent = `Page ${data.page} of ${pages} (${data.total} listings)`;
  $('#mine-prev').disabled = data.page <= 1;
  $('#mine-next').disabled = data.page >= pages;
}
$('#mine-prev').addEventListener('click', () => loadMine(minePage - 1));
$('#mine-next').addEventListener('click', () => loadMine(minePage + 1));

async function showDetail(ref, push) {
  if (!REF.test(ref || '')) return closeDetail();
  const { ok, data } = await fetchJson(`/api/v1/listings/by-ref/${encodeURIComponent(ref)}`);
  if (!ok) { say('That listing was not found.'); return closeDetail(true); }
  const l = data.listing;
  say('');
  $('#d-title').textContent = l.title; $('#d-area').textContent = l.area; $('#d-ref').textContent = l.ref;
  $('#sellerChatNote').textContent = ''; $('#d-chat').dataset.ref = l.ref;
  $('#detail').hidden = false; $('#lists').hidden = true;
  if (push && location.hash !== `#${ref}`) history.pushState(null, '', `#${ref}`);
  $('#d-chat').focus();
}

function closeDetail(keepHash) {
  $('#detail').hidden = true; $('#lists').hidden = false;
  if (!keepHash && location.hash) history.pushState(null, '', location.pathname);
}

async function submitCreate(event) {
  event.preventDefault();
  if (creating) return;
  const title = $('#c-title').value.trim(), area = $('#c-area').value.trim();
  const status = $('#c-status');
  if (title.length < 3 || title.length > 120) { status.textContent = 'Enter a title of 3 to 120 characters.'; $('#c-title').focus(); return; }
  if (area.length < 2 || area.length > 80) { status.textContent = 'Enter an area of 2 to 80 characters.'; $('#c-area').focus(); return; }
  creating = true; $('#c-submit').disabled = true; status.textContent = 'Creating…';
  try {
    const { ok, data } = await fetchJson('/api/v1/listings', { method: 'POST', body: { title, area } });
    if (!ok) { status.textContent = (data && data.error) || 'Could not create the listing.'; return; }
    const l = data.listing;
    status.textContent = `Created. Reference ${l.ref}.`;
    $('#c-title').value = ''; $('#c-area').value = '';
    await Promise.all([loadMine(), loadBrowse(true)]);
  } catch (e) { status.textContent = e.message || 'Could not reach the server.'; }
  finally { creating = false; $('#c-submit').disabled = false; }
}

async function init() {
  const me = await fetchJson('/api/v1/auth/me').catch(() => ({}));
  const sessionUser = me.ok && me.data && me.data.user;
  const guest = Boolean(sessionUser && sessionUser.role === 'guest');
  const user = sessionUser && !guest;                       // only a regular account can create or manage listings
  $('#create-form').hidden = !user; $('#login-note').hidden = Boolean(user); $('#mine-card').hidden = !user;
  $('#guest-badge').hidden = !guest; $('#messages-link').hidden = guest;   // display only: the server refuses guests anyway
  $('#create-form').addEventListener('submit', submitCreate);
  $('#more').addEventListener('click', () => { page += 1; loadBrowse(false); });
  $('#detail-close').addEventListener('click', () => closeDetail());
  $('#d-chat').addEventListener('click', () => chatWithSeller($('#d-chat').dataset.ref));
  window.addEventListener('popstate', () => { const ref = location.hash.slice(1); if (ref) showDetail(ref, false); else closeDetail(true); });
  await Promise.all([loadBrowse(true), user ? loadMine() : null]);
  if (location.hash.length > 1) showDetail(location.hash.slice(1), false);
}
init();
