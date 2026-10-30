/* services/messagesApi.js — thin client for /api/v1/messages and /api/v1/listings. No DOM. Message text is only ever
 * handed to callers as data; rendering is done with textContent, never innerHTML. */
import { fetchJson } from './http.js';

const M = '/api/v1/messages';
const unwrap = ({ ok, status, data }) => ({ ok, status, data: data || {}, error: !ok ? ((data && data.error) || 'Something went wrong. Please try again.') : '' });

export const listingByRef = async (ref) => unwrap(await fetchJson(`/api/v1/listings/by-ref/${encodeURIComponent(ref)}`));
export const openConversation = async (listingId) => unwrap(await fetchJson(`${M}/conversations`, { method: 'POST', body: { listing_id: listingId } }));
export const inbox = async (page = 1) => unwrap(await fetchJson(`${M}/conversations?page=${page}`));
export const history = async (id, { before, after, limit = 30 } = {}) => {
  const qs = new URLSearchParams({ limit });
  if (before != null) qs.set('before', before);
  if (after != null) qs.set('after', after);
  return unwrap(await fetchJson(`${M}/conversations/${encodeURIComponent(id)}?${qs}`));
};
export const sendMessage = async (id, body, clientId) => unwrap(await fetchJson(`${M}/conversations/${encodeURIComponent(id)}/messages`, { method: 'POST', body: { body, client_id: clientId } }));
export const markRead = async (id) => unwrap(await fetchJson(`${M}/conversations/${encodeURIComponent(id)}/read`, { method: 'POST', body: {} }));
export const report = async (id, reason, messageId) => unwrap(await fetchJson(`${M}/conversations/${encodeURIComponent(id)}/report`, { method: 'POST', body: { reason, message_id: messageId } }));
export const block = async (id, on = true) => unwrap(await fetchJson(`${M}/conversations/${encodeURIComponent(id)}/${on ? 'block' : 'unblock'}`, { method: 'POST', body: {} }));
export const unreadCount = async () => unwrap(await fetchJson(`${M}/unread-count`));
export const newClientId = () => `c${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
