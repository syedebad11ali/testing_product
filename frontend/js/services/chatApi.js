/* Client for POST /api/v1/chat. UI code calls only requestChatReply(). */
import { CHAT_API_URL, CHAT_FEEDBACK_URL, CHAT_TIMEOUT_MS } from '../config.js';
import { AppError } from '../core/errors.js';
import { fetchJson } from './http.js';

/** G4a2: the three authentication outcomes the server (backend/security/guards.py) can give a chat call. `kind` is 'login' for 401
 *  auth_required and 403 guest_not_allowed, 'password_change' for 403 password_change_required. Every other status/code (a plain 403
 *  forbidden, 429, 5xx, ...) is NOT an authentication outcome and keeps its existing handling. The message is fixed text: the backend's
 *  own wording is never shown. */
export class ChatAuthError extends AppError {
  constructor(kind, code) { super(kind === 'password_change' ? 'You must change your password before using the assistant.' : 'Login required.', { code }); this.name = 'ChatAuthError'; this.kind = kind; }
}
export function authFailure(status, data) {
  const code = data && typeof data.code === 'string' ? data.code : '';
  if (status === 401 && code === 'auth_required') return new ChatAuthError('login', code);
  if (status === 403 && code === 'guest_not_allowed') return new ChatAuthError('login', code);
  if (status === 403 && code === 'password_change_required') return new ChatAuthError('password_change', code);
  return null;
}

/* With `continuity` (chat cookie + Preferences consent) the server identifies the conversation itself, so no session_id is sent. */
export async function requestChatReply(sessionId, message, { reset = false, continuity = false } = {}) {
  let result;
  try {
    result = await fetchJson(CHAT_API_URL, { method: 'POST', body: continuity ? { message, reset } : { session_id: sessionId, message, reset }, timeoutMs: CHAT_TIMEOUT_MS });
  } catch (error) {
    throw new AppError(error.code === 'timeout' ? error.message : 'Could not reach Property Assistance. Check that the chatbot server is running and try again.', { code: error.code, cause: error });
  }
  const { ok, status, data } = result;
  if (!ok) { const denied = authFailure(status, data); if (denied) throw denied; }
  if (data === null) {
    throw new AppError(`Chat API returned a non-JSON response (HTTP ${status}). Start the Flask app and open http://127.0.0.1:5000, or set window.KPT_CONFIG.chatApiUrl to the deployed Flask /api/v1/chat endpoint.`, { code: 'non_json' });
  }
  if (!ok) throw new AppError(data.error || 'The assistant could not answer right now.', { code: data.code || 'http_error' });
  if (typeof data.reply !== 'string' || !data.reply.trim()) throw new AppError('The assistant returned an empty response.', { code: 'empty_reply' });
  for (const key of ['chips', 'cards', 'actions']) if (!Array.isArray(data[key])) data[key] = [];
  return data; // { reply, source, from_data, intent, specialist, chips[], cards[], actions[], memory, message_id }
}

/** Thumbs up/down for one answer. Failures are swallowed (feedback must never break the chat) except ChatAuthError, which the UI must handle. */
export async function sendFeedback(messageId, rating) {
  try {
    const { ok, status, data } = await fetchJson(CHAT_FEEDBACK_URL, { method: 'POST', body: { message_id: messageId, rating } });
    if (!ok) { const denied = authFailure(status, data); if (denied) throw denied; }
    return ok;
  } catch (error) {
    if (error instanceof ChatAuthError) throw error;   // the one exception to "never throws": the UI must react to a rejected session
    return false;
  }
}

/** Restores a returning visitor's conversation (needs Preferences consent). Throws only ChatAuthError; every other failure gives null. */
export async function fetchChatSession() {
  try {
    const { ok, status, data } = await fetchJson(CHAT_API_URL.replace(/\/chat$/, '/chat/session'));
    if (!ok) { const denied = authFailure(status, data); if (denied) throw denied; }
    return ok && data && data.continuity ? data : null;
  } catch (error) {
    if (error instanceof ChatAuthError) throw error;
    return null;
  }
}
