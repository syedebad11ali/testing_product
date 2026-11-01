/* Application state.
 *
 * State lives in a few plain, exported slices instead of ~15 loose globals. Slices are
 * never reassigned (so every importer shares the same object); use the reset helpers.
 * Rendering stays explicit (`render()`), because re-rendering on every keystroke would
 * steal input focus in the form screens.
 *
 *   state        navigation + browse filters + the signed-in account's saved properties (server-side, G5.2)
 *   ownerState   owner-verification screen (CSV store, lookup result, forecast input)
 *   docState     "Verify Your Document" wizard (step, file, OCR progress, result)
 *   docHistory   persisted verification history (files are never stored)
 *   chatState    assistant session id + transcript (sessionStorage)
 *   chatRuntime / promoRuntime   transient, non-persisted UI flags and timers
 */
import { STORAGE_KEYS } from '../config.js';
import { local, session } from '../core/storage.js';
import { sanitizeResultForStorage } from '../domain/resultPrivacy.js';
import { isAccountSession, loadSessionUser, sessionUserId } from '../services/sessionUser.js';

/* G5.2: `saved` is the CURRENT account's favorites, filled from the server after sign-in (features/favorites.js). It starts empty and is
 * never read from browser storage: the old global `kpt_favorite_properties` key is only deleted (and its content never migrated). */
local.remove(STORAGE_KEYS.favoriteProperties);
export const state = {view:'home', propId:null, featIdx:0, search:'', areaFilter:null, typeFilter:'', sort:'newest', saved:new Set()};
/** Loading state of the favorites above: status idle | loading | ready | error, the account they belong to, and the write queue. */
export const favoritesRuntime = {status:'idle', userId:null, loading:null, generation:0, queue:Promise.resolve(), noticeTimer:null};

export const ownerState = {store:null, promise:null, error:null, id:'', result:null, lookupError:'', forecastYears:'', claim:'', check:null};

export function freshDocState(){ return {step:'landing', method:null, docType:null, file:null, fields:{}, result:null, historyIndex:null, analyzeSteps:[], analyzeProgress:0, fileError:null, formError:null, cameraPhase:null, cameraStream:null, cameraFacing:'environment', cameraError:null, capturedImage:null, extraction:null, ocrText:'', ocrProgress:0, ocrPhaseLabel:'', showNotVerifiedModal:false, typeKey:null}; }
export const docState = freshDocState();
/** Reset the wizard in place so every module keeps holding the same object. */
export function resetDocState(){
  for (const key of Object.keys(docState)) delete docState[key];
  Object.assign(docState, freshDocState());
}

/* ---------- verification history: the CURRENT ACCOUNT's, device-only (G6.1b) ----------
 * The list belongs to the signed-in account and is kept in `kpt_doc_history` only while that account's session is active. The stored record is
 * {v:1, s:<random salt>, b:<digest of salt + account id>, items:[...]}: the digest only lets the page tell "mine" from "someone else's"; the
 * account id itself is never stored, and no document data beyond the already-masked results is added. A record that is not in this format
 * (the old, unowned plain array), that is bound to another account, or that is found while nobody is signed in is DELETED, never read or migrated.
 * The in-memory list is filled only after the session is known, emptied on logout / Exit / account change / expiry, and a load that finishes
 * after any of those is discarded (generation counter). */
export const docHistory = [];
export const docHistoryRuntime = {generation: 0, userId: null};

function digest(salt, id){   // equality tag, not secrecy: 53-bit cyrb53 over "salt:id" (synchronous, so it works without a secure context)
  const str = `${salt}:${id}`; let h1 = 0xdeadbeef, h2 = 0x41c6ce57;
  for (let i = 0; i < str.length; i++) { const c = str.charCodeAt(i); h1 = Math.imul(h1 ^ c, 2654435761); h2 = Math.imul(h2 ^ c, 1597334677); }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
  return (4294967296 * (2097151 & h2) + (h1 >>> 0)).toString(36);
}
const newSalt = () => (globalThis.crypto && crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`).replace(/[^0-9a-z]/gi, '').slice(0, 24);
const isRecord = (r) => r && typeof r === 'object' && !Array.isArray(r) && r.v === 1 && typeof r.s === 'string' && typeof r.b === 'string' && Array.isArray(r.items);

/** Forget the history everywhere: memory, storage, and any load still in flight. Safe to repeat. */
export function clearDocHistory(){
  docHistory.splice(0, docHistory.length);
  docHistoryRuntime.generation += 1; docHistoryRuntime.userId = null;
  local.remove(STORAGE_KEYS.docHistory);
}

/** Fill the list for the signed-in account once /auth/me has answered. Resolves true only if history was loaded for an account session that is
 * still the current one; guest / signed-out / unreachable / another account's record -> nothing shown and the record deleted. */
export function loadDocHistory(){
  const generation = ++docHistoryRuntime.generation;
  docHistory.splice(0, docHistory.length); docHistoryRuntime.userId = null;
  return loadSessionUser().catch(() => null).then((user) => {
    if (generation !== docHistoryRuntime.generation) return false;          // logout / account change / a newer load happened meanwhile
    const id = isAccountSession() ? sessionUserId() : null;
    if (!id) { local.remove(STORAGE_KEYS.docHistory); return false; }
    const record = local.getJSON(STORAGE_KEYS.docHistory, null);
    if (!isRecord(record) || record.b !== digest(record.s, id)) { local.remove(STORAGE_KEYS.docHistory); docHistoryRuntime.userId = id; return false; }
    docHistory.splice(0, docHistory.length, ...record.items.filter((r) => r && typeof r === 'object' && !Array.isArray(r)));
    docHistoryRuntime.userId = id;
    return docHistory.length > 0;
  });
}

/** True while the in-memory list belongs to the current, loaded account session. Anything else empties it first (account changed / session ended). */
export function docHistoryAllowed(){
  const id = isAccountSession() ? sessionUserId() : null;
  if (id && docHistoryRuntime.userId === id) return true;
  if (docHistory.length || docHistoryRuntime.userId) clearDocHistory();
  if (id) docHistoryRuntime.userId = id;      // a signed-in account starting an empty history
  return Boolean(id);
}

function persistDocHistory(){
  const id = sessionUserId();
  if (!id || docHistoryRuntime.userId !== id) return false;
  const old = local.getJSON(STORAGE_KEYS.docHistory, null);
  const salt = isRecord(old) && old.b === digest(old.s, id) ? old.s : newSalt();
  return local.setJSON(STORAGE_KEYS.docHistory, {v: 1, s: salt, b: digest(salt, id), items: docHistory.map(sanitizeResultForStorage)});
}
/** Add a new result at the top of the signed-in account's history; without an account session nothing is kept or stored. */
export function addDocHistory(result){
  if (!docHistoryAllowed()) return false;
  docHistory.unshift(result); persistDocHistory(); return true;
}
export function removeDocHistory(index){
  if (!docHistoryAllowed() || !Number.isInteger(index) || index < 0 || index >= docHistory.length) return false;
  docHistory.splice(index, 1); persistDocHistory(); return true;
}

/* ---------- assistant chat ---------- */
const savedChat = session.getJSON(STORAGE_KEYS.chat, {});
export const chatState = savedChat && typeof savedChat === 'object' && !Array.isArray(savedChat) ? savedChat : {};
chatState.sessionId = chatState.sessionId || (globalThis.crypto && crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`);
chatState.messages = Array.isArray(chatState.messages) ? chatState.messages : [];
export const chatRuntime = {busy:false, initialized:false};
export function saveChatState(){ session.setJSON(STORAGE_KEYS.chat, chatState); }

/* ---------- promo banner timers ---------- */
export const promoRuntime = {timer:null, lastId:null};
