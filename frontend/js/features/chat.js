/* features/chat.js — Property Assistant chat panel (UI); network calls live in services/chatApi.js. */
import { CHAT_API_URL, CHAT_STARTERS } from '../config.js';
import { requestChatReply } from '../services/chatApi.js';
import { chatRuntime, chatState, saveChatState } from '../state/store.js';

function appendChatMessage(role, text, meta){
  const thread = document.querySelector('.assistant-thread');
  if (!thread) return;
  const row = document.createElement('div');
  row.className = `chat-message ${role}`;
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
  thread.appendChild(row);
  const body = document.getElementById('chatBody');
  body.scrollTop = body.scrollHeight;
}

function renderChat(){
  const body = document.getElementById('chatBody');
  body.innerHTML = '<div class="chat-today">Today</div><div class="assistant-thread" aria-live="polite"></div><div class="assistant-starters"></div><form class="assistant-compose" autocomplete="off"><input class="assistant-input" type="text" maxlength="1000" placeholder="Ask about Karachi properties..." aria-label="Message Property Assistance"><button class="assistant-send" type="submit" aria-label="Send message" disabled>Send</button></form>';
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
    chatState.messages.forEach(message=>appendChatMessage(message.role, message.text, message.meta));
  }
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
    const data = await requestChatReply(chatState.sessionId, text);
    const meta = data.from_data ? 'From property data' : (data.source === 'greeting' ? '' : 'General knowledge');
    chatState.messages.push({role:'assistant',text:data.reply,meta});
    saveChatState();
    typing.remove();
    appendChatMessage('assistant', data.reply, meta);
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

export function openChat(){ if (!chatRuntime.initialized) renderChat(); document.getElementById('chatPanel').classList.add('open'); document.getElementById('overlayBg').classList.add('show'); }

export function closeChat(){ document.getElementById('chatPanel').classList.remove('open'); document.getElementById('overlayBg').classList.remove('show'); }
