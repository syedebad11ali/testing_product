/* features/reportTargets.js — which messages can be picked in the "Report" dialog.
 * Only messages the OTHER person sent, newest first, at most 20, labelled with a short single-line preview.
 * Pure (no DOM) so it is unit tested; the page renders the labels with textContent, never as HTML. */
export const MAX_CHOICES = 20;
const PREVIEW = 60;
const ID = /^[0-9a-f]{32}$/;

export function reportChoices(messages) {
  const out = [];
  for (let i = messages.length - 1; i >= 0 && out.length < MAX_CHOICES; i--) {
    const m = messages[i];
    if (!m || m.mine || typeof m.id !== 'string' || !ID.test(m.id)) continue;
    const flat = String(m.body ?? '').replace(/\s+/g, ' ').trim();
    out.push({ id: m.id, label: flat.length > PREVIEW ? `${flat.slice(0, PREVIEW - 1)}…` : flat || '(empty message)' });
  }
  return out;
}
