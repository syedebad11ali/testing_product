/* Messages page: inbox, conversation, composer. Updates by polling every few seconds while the tab is visible
 * (this is NOT real-time push). Every piece of message text is written with textContent, never as markup. */
import { reportChoices } from './features/reportTargets.js';
import { block, history, inbox, markRead, newClientId, openConversation, listingByRef, report, sendMessage } from './services/messagesApi.js';

const $ = (s) => document.querySelector(s);
const POLL_MS = 6000;
let current = null;      // {id, newest, oldest, hasMore}
let pollTimer = null;
let sending = false;

const say = (t) => { $('#msg').textContent = t || ''; };
const state = (t) => { $('#state').textContent = t || ''; };
const when = (us) => new Date(us / 1000).toLocaleString();

function bubble(m) {
  const li = document.createElement('li');
  li.className = `msg-bubble${m.mine ? ' mine' : ''}`;
  li.dataset.id = m.id;
  const text = document.createElement('span'); text.textContent = m.body;
  const time = document.createElement('time'); time.textContent = when(m.ts);
  li.append(text, time);
  return li;
}

async function loadInbox() {
  const r = await inbox();
  if (!r.ok) { if (r.status === 401) location.assign('/login?next=/messages'); else say(r.error); return; }
  const list = $('#inbox'); list.replaceChildren();
  $('#inboxEmpty').hidden = r.data.conversations.length > 0;
  for (const c of r.data.conversations) {
    const li = document.createElement('li'); const b = document.createElement('button');
    b.type = 'button'; b.className = 'msg-item'; if (current && current.id === c.id) b.setAttribute('aria-current', 'true');
    const who = document.createElement('b'); who.textContent = c.counterpart;
    if (c.unread) { const badge = document.createElement('span'); badge.className = 'msg-badge'; badge.textContent = `${c.unread} new`; who.appendChild(badge); }
    const subject = document.createElement('small'); subject.textContent = c.listing.title || 'Listing';
    const preview = document.createElement('span'); preview.textContent = c.last_message.preview ? `${c.last_message.mine ? 'You: ' : ''}${c.last_message.preview}` : 'No messages yet';
    b.append(who, subject, preview); b.addEventListener('click', () => openThread(c.id)); li.appendChild(b); list.appendChild(li);
  }
}

function scrollEnd() { const s = $('#scroll'); s.scrollTop = s.scrollHeight; }

async function openThread(id) {
  say(''); state('');
  const r = await history(id);
  if (!r.ok) { say(r.error); return; }
  current = { id, newest: 0, oldest: null, hasMore: r.data.has_more };
  const c = r.data.conversation;
  $('#peer').textContent = c.counterpart; $('#subject').textContent = c.listing.title || '';
  $('#thread').hidden = false; $('.msg-layout').classList.add('in-thread');
  const ol = $('#messages'); ol.replaceChildren();
  for (const m of r.data.messages) ol.appendChild(bubble(m));
  if (r.data.messages.length) { current.oldest = r.data.messages[0].ts; current.newest = r.data.messages.at(-1).ts; }
  $('#older').hidden = !r.data.has_more;
  setBlockState(Boolean(c.blocked_by_me));
  $('#composer').querySelector('textarea').disabled = !c.counterpart_available;
  state(c.blocked_by_me ? 'You blocked this person. Unblock them to continue.' : c.counterpart_available ? '' : 'This conversation is closed for new messages.');
  scrollEnd(); await markRead(id); loadInbox(); schedulePoll();
}

async function older() {
  if (!current || current.oldest == null) return;
  const r = await history(current.id, { before: current.oldest });
  if (!r.ok) { say(r.error); return; }
  const ol = $('#messages');
  for (const m of [...r.data.messages].reverse()) ol.prepend(bubble(m));
  if (r.data.messages.length) current.oldest = r.data.messages[0].ts;
  $('#older').hidden = !r.data.has_more;
}

async function poll() {
  if (!current || document.hidden) return schedulePoll();
  const r = await history(current.id, { after: current.newest });
  if (r.ok && r.data.messages.length) {
    const ol = $('#messages'); const known = new Set([...ol.children].map((li) => li.dataset.id));
    for (const m of r.data.messages) if (!known.has(m.id)) ol.appendChild(bubble(m));
    current.newest = r.data.messages.at(-1).ts; scrollEnd(); markRead(current.id); loadInbox();
  }
  schedulePoll();
}
function schedulePoll() { clearTimeout(pollTimer); pollTimer = setTimeout(poll, POLL_MS); }

async function submit(event) {
  event.preventDefault();
  if (sending || !current) return;
  const box = $('#body'); const text = box.value.trim();
  if (!text) { state('Write a message first.'); return; }
  sending = true; $('#send').disabled = true; state('Sending…');
  const r = await sendMessage(current.id, text, box.dataset.cid || (box.dataset.cid = newClientId()));  // same id on retry = no duplicate
  sending = false; $('#send').disabled = false;
  if (!r.ok) { state(r.status === 429 ? 'You are sending too fast. Please wait a moment.' : r.error); return; }
  box.value = ''; delete box.dataset.cid; state('');
  const fresh = await history(current.id, { after: current.newest });
  if (fresh.ok) { const ol = $('#messages'); for (const m of fresh.data.messages) ol.appendChild(bubble(m)); if (fresh.data.messages.length) current.newest = fresh.data.messages.at(-1).ts; }
  scrollEnd(); loadInbox();
}

async function start() {
  const params = new URLSearchParams(location.search);
  await loadInbox();
  let target = params.get('c');
  if (!target && params.get('listing')) {  // returned from login with a listing in hand
    const found = await listingByRef(params.get('listing'));
    if (found.ok && found.data.listing.contactable && !found.data.listing.own) {
      const opened = await openConversation(found.data.listing.id);
      if (opened.ok) target = opened.data.conversation.id; else say(opened.error);
    } else if (!found.ok) say('That listing is not available for messages.');
  }
  if (target) await openThread(target);
}

$('#composer').addEventListener('submit', submit);
$('#older').addEventListener('click', older);
$('#back').addEventListener('click', () => { current = null; $('#thread').hidden = true; $('.msg-layout').classList.remove('in-thread'); loadInbox(); });

/** Accessible in-page dialog (native <dialog>: focus trap, Esc to cancel). Resolves to the entered text, true, or null on cancel. */
/** Fill the optional "what are you reporting?" menu from the bubbles on screen (the other person's messages only). */
function fillTargets(select) {
  const msgs = [...$('#messages').children].map((li) => ({ id: li.dataset.id, mine: li.classList.contains('mine'), body: li.firstChild ? li.firstChild.textContent : '' }));
  select.replaceChildren();
  const whole = document.createElement('option'); whole.value = ''; whole.textContent = 'The whole conversation'; select.appendChild(whole);
  for (const c of reportChoices(msgs)) { const o = document.createElement('option'); o.value = c.id; o.textContent = `Message: ${c.label}`; select.appendChild(o); }
}

function ask({ title, text, field = false, confirm = 'Confirm', target = false }) {
  const dlg = $('#dlg'), input = $('#dlg-input'), err = $('#dlg-err'), form = $('#dlg-form');
  $('#dlg-target').hidden = !target;
  if (target) fillTargets($('#dlg-target-select'));
  $('#dlg-title').textContent = title; $('#dlg-text').textContent = text; $('#dlg-ok').textContent = confirm;
  $('#dlg-field').hidden = !field; input.value = ''; err.textContent = '';
  return new Promise((resolve) => {
    const done = (value) => { form.removeEventListener('submit', onSubmit); $('#dlg-cancel').removeEventListener('click', onCancel); dlg.removeEventListener('cancel', onCancel); dlg.close(); resolve(value); };
    const onSubmit = (e) => {
      e.preventDefault();
      if (field) { const v = input.value.trim(); if (v.length < 3 || v.length > 500) { err.textContent = 'Please describe the problem in 3 to 500 characters.'; input.focus(); return; } return done(target ? { reason: v, messageId: $('#dlg-target-select').value || undefined } : v); }
      done(true);
    };
    const onCancel = (e) => { if (e) e.preventDefault(); done(null); };
    form.addEventListener('submit', onSubmit); $('#dlg-cancel').addEventListener('click', onCancel); dlg.addEventListener('cancel', onCancel);
    dlg.showModal(); (field ? input : $('#dlg-ok')).focus();
  });
}

function setBlockState(blocked) { $('#block').hidden = blocked; $('#unblock').hidden = !blocked; }

$('#report').addEventListener('click', async () => {
  if (!current) return;
  const picked = await ask({ title: 'Report this conversation', text: 'Tell us what is wrong. A moderator will review the reported conversation. The other person is not told who reported.', field: true, confirm: 'Send report', target: true });
  if (!picked || !current) return;
  state('Sending report…');
  const r = await report(current.id, picked.reason, picked.messageId);
  state(r.ok ? 'Thank you. Our moderators will review this conversation.' : r.error);
});
$('#block').addEventListener('click', async () => {
  if (!current) return;
  const yes = await ask({ title: 'Block this person?', text: 'Neither of you will be able to send messages in this conversation. You can unblock them here later. Existing messages stay.', confirm: 'Block' });
  if (!yes || !current) return;
  const r = await block(current.id, true);
  if (r.ok) { setBlockState(true); $('#composer').querySelector('textarea').disabled = true; state('Blocked. You can unblock this person from the toolbar.'); } else state(r.error);
});
$('#unblock').addEventListener('click', async () => {
  if (!current) return;
  const yes = await ask({ title: 'Unblock this person?', text: 'You will both be able to send messages in this conversation again.', confirm: 'Unblock' });
  if (!yes || !current) return;
  const r = await block(current.id, false);
  if (r.ok) { setBlockState(false); $('#composer').querySelector('textarea').disabled = false; state('Unblocked.'); } else state(r.error);
});
document.addEventListener('visibilitychange', () => { if (!document.hidden && current) poll(); });
start();
