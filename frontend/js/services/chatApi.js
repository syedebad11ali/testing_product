/* Client for POST /api/v1/chat. UI code calls only requestChatReply(). */
import { CHAT_API_URL, CHAT_FEEDBACK_URL, CHAT_TIMEOUT_MS } from '../config.js';
import { AppError } from '../core/errors.js';
import { fetchJson } from './http.js';

/* With `continuity` (chat cookie + Preferences consent) the server identifies the conversation itself, so no session_id is sent. */
export async function requestChatReply(sessionId, message, { reset = false, continuity = false } = {}) {
  let result;
  try {
    result = await fetchJson(CHAT_API_URL, { method: 'POST', body: continuity ? { message, reset } : { session_id: sessionId, message, reset }, timeoutMs: CHAT_TIMEOUT_MS });
  } catch (error) {
    throw new AppError(error.code === 'timeout' ? error.message : 'Could not reach Property Assistance. Check that the chatbot server is running and try again.', { code: error.code, cause: error });
  }
  const { ok, status, data } = result;
  if (data === null) {
    throw new AppError(`Chat API returned a non-JSON response (HTTP ${status}). Start the Flask app and open http://127.0.0.1:5000, or set window.KPT_CONFIG.chatApiUrl to the deployed Flask /api/v1/chat endpoint.`, { code: 'non_json' });
  }
  if (!ok) throw new AppError(data.error || 'The assistant could not answer right now.', { code: data.code || 'http_error' });
  if (typeof data.reply !== 'string' || !data.reply.trim()) throw new AppError('The assistant returned an empty response.', { code: 'empty_reply' });
  for (const key of ['chips', 'cards', 'actions']) if (!Array.isArray(data[key])) data[key] = [];
  return data; // { reply, source, from_data, intent, specialist, chips[], cards[], actions[], memory, message_id }
}

/** Thumbs up/down for one answer. Failures are swallowed: feedback must never break the chat. */
export async function sendFeedback(messageId, rating) {
  try {
    const { ok } = await fetchJson(CHAT_FEEDBACK_URL, { method: 'POST', body: { message_id: messageId, rating } });
    return ok;
  } catch (_) { return false; }
}

/** Restores a returning visitor's conversation (needs Preferences consent). Never throws. */
export async function fetchChatSession() {
  try {
    const { ok, data } = await fetchJson(CHAT_API_URL.replace(/\/chat$/, '/chat/session'));
    return ok && data && data.continuity ? data : null;
  } catch (_) { return null; }
}
