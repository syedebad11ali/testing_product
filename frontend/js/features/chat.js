/* features/chat.js — Property Assistant chat panel (UI); network calls live in services/chatApi.js. */
import { CHAT_API_URL, CHAT_STARTERS } from '../config.js';
import { render, routeFromHash } from '../app/router.js';
import { ChatAuthError, fetchChatSession, requestChatReply, sendFeedback } from '../services/chatApi.js';
import { chatRuntime, chatState, saveChatState } from '../state/store.js';
import { showLoginRequired } from './loginPrompt.js';
import { isAccountUser, loadSessionUser, resetSessionUser } from '../services/sessionUser.js';

/* G4a2: authentication errors from /chat, /chat/session and /chat/feedback (the session expired or became invalid while the panel was
 * in use). 401 auth_required and 403 guest_not_allowed -> the shared login dialog; 403 password_change_required -> the existing forced
 * password-change page (backend/web.py and api/auth.py send users there too). Anything else is not handled here. */
export const PASSWORD_CHANGE_URL = '/login?change=1';
let authEpoch = 0;        // bumped on every rejection; an operation that started before the bump must not touch the UI or the history
let leaving = false;      // one navigation to the password-change page, however many pending requests fail together

/** @returns {boolean} true when `error` was an authentication outcome and has been handled (the caller then shows nothing else) */
function handleAuthError(error){
  if (!(error instanceof ChatAuthError)) return false;
  authEpoch += 1;
  if (error.kind === 'password_change') {
    if (!leaving) { leaving = true; globalThis.location.assign(PASSWORD_CHANGE_URL); }
  } else {
    resetSessionUser();   // forget only the cached /auth/me answer so the next launch re-checks it; the server session itself is not touched
    showLoginRequired({ feature: 'Property Assistant' });   // an open dialog is reused: never two
  }
  return true;
}

/* Only these link shapes may become an href: server-built listing deep links, site pages, WhatsApp, mailto. */
const SAFE_URL = /^(\/#\/(?:plot|house|apartment|portion|commercial|property)\/DEMO-KPT-\d+|\/#verify-document|\/#owner-verification|\/login|https:\/\/wa\.me\/\d+\?text=\S*|mailto:\S+)$/;
export function safeUrl(url){ return typeof url === 'string' && SAFE_URL.test(url) ? url : null; }

function link(className, url, onInternal){
  const a = document.createElement('a');
  a.className = className;
  a.href = url;
  if (url.startsWith('/#')) a.addEventListener('click', event=>{
    event.preventDefault();
    history.pushState(null, '', url);
    routeFromHash(url.slice(1)).then((applied) => { if (applied) render(); });
    closeChat();
  });
  return a;
}

function chipButton(label, onClick){
  const b = document.createElement('button');
  b.type = 'button'; b.className = 'chat-chip'; b.textContent = label;
  b.addEventListener('click', onClick);
  return b;
}

function renderExtras(row, extras){
  if (extras.cards && extras.cards.length) {
    const wrap = document.createElement('div'); wrap.className = 'chat-cards';
    extras.cards.forEach(card=>{
      const url = safeUrl(card.url); if (!url) return;
      const a = link('chat-card', url);
      const title = document.createElement('strong'); title.textContent = card.title || card.id;
      const price = document.createElement('span'); price.className = 'cc-price'; price.textContent = card.price || '';
      a.append(title, price);
      if (Array.isArray(card.why) && card.why.length) {
        const ul = document.createElement('ul');
        card.why.slice(0, 4).forEach(w=>{ const li = document.createElement('li'); li.textContent = String(w); ul.appendChild(li); });
        a.appendChild(ul);
      }
      wrap.appendChild(a);
    });
    row.appendChild(wrap);
  }
  if (extras.actions && extras.actions.length) {
    const wrap = document.createElement('div'); wrap.className = 'chat-actions';
    extras.actions.forEach(act=>{ const url = safeUrl(act.url); if (!url) return; const a = link('chat-action', url); a.textContent = String(act.label || 'Open'); wrap.appendChild(a); });
    row.appendChild(wrap);
  }
  if (extras.chips && extras.chips.length && extras.isLast) {
    const wrap = document.createElement('div'); wrap.className = 'chat-chips'; wrap.setAttribute('role', 'group'); wrap.setAttribute('aria-label', 'Suggested replies');
    extras.chips.forEach(chip=>{
      const url = safeUrl(chip.url);
      if (url) { const a = link('chat-chip', url); a.textContent = String(chip.label); wrap.appendChild(a); }
      else if (typeof chip.message === 'string') wrap.appendChild(chipButton(String(chip.label), ()=>sendChatMessage(chip.message)));
    });
    row.appendChild(wrap);
  }
  if (extras.messageId) {
    const fb = document.createElement('div'); fb.className = 'chat-feedback';
    [['up', '👍', 'Helpful'], ['down', '👎', 'Not helpful']].forEach(([rating, icon, label])=>{
      const b = document.createElement('button'); b.type = 'button'; b.textContent = icon; b.setAttribute('aria-label', label); b.setAttribute('aria-pressed', 'false');
      b.addEventListener('click', ()=>{ fb.querySelectorAll('button').forEach(x=>{ x.disabled = true; }); b.setAttribute('aria-pressed', 'true'); sendFeedback(extras.messageId, rating).catch(error=>{ if (handleAuthError(error)) { fb.querySelectorAll('button').forEach(x=>{ x.disabled = false; }); b.setAttribute('aria-pressed', 'false'); } }); });
      fb.appendChild(b);
    });
    row.appendChild(fb);
  }
}

function appendChatMessage(role, text, meta, extras = {}){
  const thread = document.querySelector('.assistant-thread');
  if (!thread) return;
  if (extras.isLast) document.querySelectorAll('.chat-chips').forEach(node=>node.remove());
  const row = document.createElement('div');
  row.className = `chat-message ${role}`;
  if (extras.specialist) {
    const tag = document.createElement('div'); tag.className = 'chat-specialist';
    tag.textContent = `Handing you to the ${extras.specialist}…`; row.appendChild(tag);
  }
  const bubble = document.createElement('div');
  bubble.className = 'chat-message-bubble';
  bubble.textContent = text;
  row.appendChild(bubble);
  if (meta) {
    const note = document.createElement('div');
    note.className = 'chat-message-meta';
    note.textContent = meta;
    row.appendChild(note);
  }
  renderExtras(row, extras);
  thread.appendChild(row);
  const body = document.getElementById('chatBody');
  body.scrollTop = body.scrollHeight;
}

/** Start over: new anonymous session id (the server forgets the old memory) and a clean transcript. */
export async function resetChat(){
  if (chatState.continuity) {   // the server keeps this conversation: ask it to clear it and send a fresh greeting
    const epoch = authEpoch;
    try {
      const data = await requestChatReply(chatState.sessionId, 'hello', { reset: true, continuity: true });
      if (epoch !== authEpoch) return;   // access was rejected meanwhile: leave the transcript as it is
      chatState.messages = [{ role: 'assistant', text: data.reply, extras: { chips: data.chips.slice(0, 5) } }];
      chatState.lastSpecialist = ''; saveChatState(); renderChat(); return;
    } catch (error) { if (handleAuthError(error) || epoch !== authEpoch) return; /* history is kept when access is rejected; any other failure falls through to a local reset */ }
  }
  chatState.sessionId = globalThis.crypto && crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
  chatState.messages = []; chatState.lastSpecialist = '';
  saveChatState();
  renderChat();
}

function renderChat(){
  const body = document.getElementById('chatBody');
  body.innerHTML = '<button type="button" class="assistant-reset">Start over</button><div class="chat-today">Today</div><div class="assistant-thread" aria-live="polite"></div><div class="assistant-starters"></div><form class="assistant-compose" autocomplete="off"><input class="assistant-input" type="text" maxlength="1000" placeholder="Ask about Karachi properties..." aria-label="Message Property Assistance"><button class="assistant-send" type="submit" aria-label="Send message" disabled>Send</button></form>';
  chatRuntime.initialized = true;
  if (!chatState.messages.length) {
    appendChatMessage('assistant', 'Assalam o Alaikum! I can estimate property prices, compare areas and search our property records. How can I help?');
    CHAT_STARTERS.forEach(text=>{
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'assistant-starter';
      button.textContent = text;
      button.addEventListener('click', ()=>sendChatMessage(text));
      body.querySelector('.assistant-starters').appendChild(button);
    });
  } else {
    const lastAssistant = chatState.messages.map(m=>m.role).lastIndexOf('assistant');
    chatState.messages.forEach((message, index)=>appendChatMessage(message.role, message.text, message.meta, message.role === 'assistant' ? { ...message.extras, isLast: index === lastAssistant } : {}));
  }
  body.querySelector('.assistant-reset').addEventListener('click', resetChat);
  const form = body.querySelector('.assistant-compose');
  const input = body.querySelector('.assistant-input');
  const send = body.querySelector('.assistant-send');
  input.addEventListener('input', ()=>{ send.disabled = !input.value.trim() || chatRuntime.busy; });
  form.addEventListener('submit', event=>{
    event.preventDefault();
    const text = input.value;
    input.value = '';
    send.disabled = true;
    sendChatMessage(text);
  });
}

async function sendChatMessage(text){
  text = text.trim();
  if (!text || chatRuntime.busy) return;
  chatRuntime.busy = true;
  document.querySelectorAll('.assistant-starter').forEach(button=>button.remove());
  chatState.messages.push({role:'user',text});
  saveChatState();
  appendChatMessage('user', text);
  const thread = document.querySelector('.assistant-thread');
  const typing = document.createElement('div');
  typing.className = 'chat-message assistant chat-typing';
  typing.setAttribute('role', 'status');
  typing.setAttribute('aria-label', 'Property Assistance is typing');
  const typingBubble = document.createElement('div');
  typingBubble.className = 'chat-message-bubble';
  typingBubble.setAttribute('aria-hidden', 'true');
  for (let index = 0; index < 3; index++) {
    const dot = document.createElement('span');
    dot.className = 'chat-typing-dot';
    typingBubble.appendChild(dot);
  }
  typing.appendChild(typingBubble);
  thread.appendChild(typing);
  const send = document.querySelector('.assistant-send');
  if (send) send.disabled = true;
  const epoch = authEpoch;
  try {
    const data = await requestChatReply(chatState.sessionId, text, { continuity: chatState.continuity === true });
    if (epoch !== authEpoch) { typing.remove(); return; }   // access was rejected while this was pending: no reply is inserted
    chatState.continuity = data.continuity === true;
    const meta = data.from_data ? 'From property data' : (data.source === 'greeting' ? '' : 'General knowledge');
    const showSpecialist = data.specialist && data.specialist !== 'Property Assistant' && data.specialist !== chatState.lastSpecialist ? data.specialist : '';
    chatState.lastSpecialist = data.specialist || '';
    const extras = { specialist: showSpecialist, cards: data.cards.slice(0, 4), chips: data.chips.slice(0, 5), actions: data.actions.slice(0, 3), messageId: data.message_id };
    chatState.messages.push({role:'assistant',text:data.reply,meta,extras});
    saveChatState();
    typing.remove();
    appendChatMessage('assistant', data.reply, meta, { ...extras, isLast: true });
  } catch (error) {
    typing.remove();
    if (handleAuthError(error) || epoch !== authEpoch) return;   // login / password-change flow instead of a message; stale failures stay silent
    appendChatMessage('error', error.message || 'Could not reach Property Assistance. Check that the chatbot server is running and try again.');
  } finally {
    chatRuntime.busy = false;
    const input = document.querySelector('.assistant-input');
    const currentSend = document.querySelector('.assistant-send');
    if (input && currentSend) currentSend.disabled = !input.value.trim();
  }
}

/** Returning visitor with Preferences consent: bring back the stored conversation and a welcome-back line. */
async function restoreChatSession(){
  if (chatRuntime.restored) return;
  chatRuntime.restored = true;
  const epoch = authEpoch;
  let data;
  try { data = await fetchChatSession(); } catch (error) { if (handleAuthError(error)) chatRuntime.restored = false; return; }   // restore again on a later, user-initiated open
  if (epoch !== authEpoch) { chatRuntime.restored = false; return; }   // access was rejected while this was pending: do not touch the transcript
  if (!data) return;
  chatState.continuity = true;
  if (chatState.messages.length) { saveChatState(); return; }   // this tab already shows its own transcript
  const past = (data.history || []).map(h => ({ role: h.role === 'user' ? 'user' : 'assistant', text: String(h.text || '') }));
  const w = data.welcome;
  if (w) past.push({ role: 'assistant', text: String(w.text || ''), extras: { chips: Array.isArray(w.chips) ? w.chips.slice(0, 5) : [] } });
  if (!past.length) return;
  chatState.messages = past; saveChatState(); renderChat();
}

/** G4a1: the Property Assistant is an account feature. Every launch button (floating button, drawer entry, "Learn how verification works",
 *  "Ask the assistant", "Contact Seller", "Share") reaches the panel through openChat(), so the guard lives here. It awaits the one existing
 *  GET /auth/me; only a loaded registered user or admin opens the panel. A guest, a signed-out visitor, or a session that cannot be resolved
 *  gets the existing login dialog (an open dialog is reused, so never a second one): no panel, no chat API request, no history change, and
 *  the guest session is left alone. Display only: the server still answers 401/403 on /chat. Resolves true when the panel was opened. */
export async function openChat(){
  let user = null;
  try { user = await loadSessionUser(); } catch { user = null; }
  if (!isAccountUser(user)) { showLoginRequired({ feature: 'Property Assistant' }); return false; }
  openChatPanel();
  return true;
}

function openChatPanel(){ leaving = false; if (!chatRuntime.initialized) renderChat(); restoreChatSession(); document.getElementById('chatPanel').classList.add('open'); document.getElementById('overlayBg').classList.add('show'); }

export function closeChat(){ document.getElementById('chatPanel').classList.remove('open'); document.getElementById('overlayBg').classList.remove('show'); }
