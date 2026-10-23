/* Client for POST /api/v1/chat. UI code calls only requestChatReply(). */
import { CHAT_API_URL, CHAT_TIMEOUT_MS } from '../config.js';
import { AppError } from '../core/errors.js';
import { fetchJson } from './http.js';

export async function requestChatReply(sessionId, message) {
  let result;
  try {
    result = await fetchJson(CHAT_API_URL, { method: 'POST', body: { session_id: sessionId, message }, timeoutMs: CHAT_TIMEOUT_MS });
  } catch (error) {
    throw new AppError(error.code === 'timeout' ? error.message : 'Could not reach Property Assistance. Check that the chatbot server is running and try again.', { code: error.code, cause: error });
  }
  const { ok, status, data } = result;
  if (data === null) {
    throw new AppError(`Chat API returned a non-JSON response (HTTP ${status}). Start the Flask app and open http://127.0.0.1:5000, or set window.KPT_CONFIG.chatApiUrl to the deployed Flask /api/v1/chat endpoint.`, { code: 'non_json' });
  }
  if (!ok) throw new AppError(data.error || 'The assistant could not answer right now.', { code: data.code || 'http_error' });
  if (typeof data.reply !== 'string' || !data.reply.trim()) throw new AppError('The assistant returned an empty response.', { code: 'empty_reply' });
  return data; // { reply, source, from_data }
}
