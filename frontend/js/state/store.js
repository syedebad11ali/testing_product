/* Application state.
 *
 * State lives in a few plain, exported slices instead of ~15 loose globals. Slices are
 * never reassigned (so every importer shares the same object); use the reset helpers.
 * Rendering stays explicit (`render()`), because re-rendering on every keystroke would
 * steal input focus in the form screens.
 *
 *   state        navigation + browse filters + saved properties
 *   ownerState   owner-verification screen (CSV store, lookup result, forecast input)
 *   docState     "Verify Your Document" wizard (step, file, OCR progress, result)
 *   docHistory   persisted verification history (files are never stored)
 *   chatState    assistant session id + transcript (sessionStorage)
 *   chatRuntime / promoRuntime   transient, non-persisted UI flags and timers
 */
import { STORAGE_KEYS } from '../config.js';
import { local, session } from '../core/storage.js';

export const state = {view:'home', propId:null, search:'', areaFilter:null, typeFilter:'', sort:'newest', saved:new Set()};

export const ownerState = {store:null, promise:null, error:null, id:'', result:null, lookupError:'', forecastYears:''};

export function freshDocState(){ return {step:'landing', method:null, docType:null, file:null, fields:{}, result:null, historyIndex:null, analyzeSteps:[], analyzeProgress:0, fileError:null, formError:null, cameraPhase:null, cameraStream:null, cameraFacing:'environment', cameraError:null, capturedImage:null, extraction:null, ocrText:'', ocrProgress:0, ocrPhaseLabel:'', showNotVerifiedModal:false, typeKey:null}; }
export const docState = freshDocState();
/** Reset the wizard in place so every module keeps holding the same object. */
export function resetDocState(){
  for (const key of Object.keys(docState)) delete docState[key];
  Object.assign(docState, freshDocState());
}

/* ---------- persisted verification history (files are never stored) ---------- */
export const docHistory = [];
export function loadDocHistory(){
  const saved = local.getJSON(STORAGE_KEYS.docHistory, []);
  docHistory.splice(0, docHistory.length, ...(Array.isArray(saved) ? saved : []));
}
export function saveDocHistory(){ local.setJSON(STORAGE_KEYS.docHistory, docHistory); }

/* ---------- assistant chat ---------- */
const savedChat = session.getJSON(STORAGE_KEYS.chat, {});
export const chatState = savedChat && typeof savedChat === 'object' && !Array.isArray(savedChat) ? savedChat : {};
chatState.sessionId = chatState.sessionId || (globalThis.crypto && crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`);
chatState.messages = Array.isArray(chatState.messages) ? chatState.messages : [];
export const chatRuntime = {busy:false, initialized:false};
export function saveChatState(){ session.setJSON(STORAGE_KEYS.chat, chatState); }

/* ---------- promo banner timers ---------- */
export const promoRuntime = {timer:null, lastId:null};
