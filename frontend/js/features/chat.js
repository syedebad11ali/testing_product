/* features/chat.js — Property Assistant chat panel (UI); network calls live in services/chatApi.js. */
import { CHAT_API_URL, CHAT_STARTERS } from '../config.js';
import { render, routeFromHash } from '../app/router.js';
import { fetchChatSession, requestChatReply, sendFeedback } from '../services/chatApi.js';
import { chatRuntime, chatState, saveChatState } from '../state/store.js';

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
    if (routeFromHash(url.slice(1))) render();
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
      b.addEventListener('click', ()=>{ fb.querySelectorAll('button').forEach(x=>{ x.disabled = true; }); b.setAttribute('aria-pressed', 'true'); sendFeedback(extras.messageId, rating); });
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
    try {
      const data = await requestChatReply(chatState.sessionId, 'hello', { reset: true, continuity: true });
      chatState.messages = [{ role: 'assistant', text: data.reply, extras: { chips: data.chips.slice(0, 5) } }];
      chatState.lastSpecialist = ''; saveChatState(); renderChat(); return;
    } catch (_) { /* fall through to a local reset */ }
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
  try {
    const data = await requestChatReply(chatState.sessionId, text, { continuity: chatState.continuity === true });
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
  const data = await fetchChatSession();
  if (!data) return;
  chatState.continuity = true;
  if (chatState.messages.length) { saveChatState(); return; }   // this tab already shows its own transcript
  const past = (data.history || []).map(h => ({ role: h.role === 'user' ? 'user' : 'assistant', text: String(h.text || '') }));
  const w = data.welcome;
  if (w) past.push({ role: 'assistant', text: String(w.text || ''), extras: { chips: Array.isArray(w.chips) ? w.chips.slice(0, 5) : [] } });
  if (!past.length) return;
  chatState.messages = past; saveChatState(); renderChat();
}

export function openChat(){ if (!chatRuntime.initialized) renderChat(); restoreChatSession(); document.getElementById('chatPanel').classList.add('open'); document.getElementById('overlayBg').classList.add('show'); }

export function closeChat(){ document.getElementById('chatPanel').classList.remove('open'); document.getElementById('overlayBg').classList.remove('show'); }
