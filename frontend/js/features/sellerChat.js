/* features/sellerChat.js — "Chat with seller" on a property: decides where the button leads. Pure decision logic is
 * exported for tests; the DOM part only writes a short status line (textContent). */
import { fetchJson } from '../services/http.js';
import { listingByRef, openConversation } from '../services/messagesApi.js';

/** @returns {Promise<{action:'login'|'open'|'unavailable'|'own'|'error', url?:string, note?:string}>} */
export async function decideSellerChat(propertyRef, api = { listingByRef, openConversation, me: () => fetchJson('/api/v1/auth/me') }) {
  try {
    const found = await api.listingByRef(propertyRef);
    if (found.status === 404) return { action: 'unavailable', note: 'Private messaging is not available for this listing yet. You can still use the assistant.' };
    if (!found.ok) return { action: 'error', note: found.error };
    const listing = found.data.listing;
    if (listing.own) return { action: 'own', note: 'This is your own listing. Open your inbox to reply to buyers.', url: '/messages' };
    if (!listing.contactable) return { action: 'unavailable', note: 'This seller cannot be messaged right now.' };
    const me = await api.me();
    const loginUrl = `/login?next=${encodeURIComponent(`/messages?listing=${propertyRef}`)}`;
    if (!(me.ok && me.data && me.data.user)) return { action: 'login', url: loginUrl };
    if (me.data.user.role === 'guest') return { action: 'guest', url: loginUrl, note: 'Messaging sellers needs a free account.' };
    const opened = await api.openConversation(listing.id);
    if (!opened.ok) return { action: 'error', note: opened.error };
    return { action: 'open', url: `/messages?c=${opened.data.conversation.id}` };
  } catch (_) {
    return { action: 'error', note: 'Could not reach the server. Check your connection and try again.' };
  }
}

export async function chatWithSeller(propertyRef) {
  const note = document.getElementById('sellerChatNote');
  if (note) note.textContent = 'Opening chat…';
  const result = await decideSellerChat(propertyRef);
  if (result.url && result.action !== 'own' && result.action !== 'guest') { window.location.assign(result.url); return; }
  if (note) {
    note.textContent = result.note || '';
    if (result.action === 'guest') {   // stay on the page and offer the way forward (DOM nodes only, no HTML strings)
      for (const [label, href] of [[' Log in', result.url], [' or sign up', '/signup']]) { const a = document.createElement('a'); a.href = href; a.textContent = label; note.append(a); }
    }
  }
}
