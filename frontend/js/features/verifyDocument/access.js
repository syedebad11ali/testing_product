/* features/verifyDocument/access.js — G6.1a: document verification is an account feature.
 *
 * The router already gates the *views* (nav / routeFromHash), but an action function can also be called directly (devtools, an
 * injected data-onclick). So every action that opens the camera or a file, picks a method/type, starts extraction or verification,
 * opens the evidence screens or enters manual checking begins with:
 *
 *     if(!isAccountSession()) return gateThen(() => sameFunction(sameArguments));
 *
 * - A loaded registered user / admin passes through synchronously: nothing changes for them.
 * - Anyone else (guest, signed-out, session not loaded yet, /auth/me unreachable) waits for the one session answer. Only a registered
 *   account re-runs the action; every other outcome shows the shared "Login required" dialog and the action never runs, so no camera
 *   permission is requested, no file is read and no state is changed first. Fails closed. */
import { isAccountSession, isAccountUser, loadSessionUser } from '../../services/sessionUser.js';
import { showLoginRequired } from '../loginPrompt.js';

export const DOCUMENT_FEATURE = 'Document verification';

/** @param {() => any} retry the original action; @returns {Promise<any>} resolves to its result, or undefined when refused */
export function gateThen(retry) {
  return loadSessionUser().catch(() => null).then((user) => {
    if (isAccountUser(user) && isAccountSession()) return retry();
    showLoginRequired({ feature: DOCUMENT_FEATURE });   // an already-open dialog is reused: never two
    return undefined;
  });
}
