/* features/creators.js - closes the header "Creators" <details> menu on Escape, on an outside click and when a link is used.
 * The menu itself is plain HTML (details/summary works without JS); this only adds the expected dismiss behaviour. */

/** Pure decision helper (unit-tested): should this event close the open menu? */
export function shouldClose(event, menu) {
  if (!menu || !menu.open) return false;
  if (event.type === 'keydown') return event.key === 'Escape';
  const target = event.target;
  if (!target || typeof menu.contains !== 'function') return false;
  if (!menu.contains(target)) return true;
  return Boolean(target.closest && target.closest('.creators-dropdown a'));
}

export function initCreatorsMenu(doc = document) {
  const menu = doc.getElementById('creatorsMenu');
  if (!menu) return null;
  const handler = (event) => {
    if (!shouldClose(event, menu)) return;
    menu.open = false;
    if (event.type === 'keydown') menu.querySelector('summary')?.focus();  // return focus to the control that opened it
  };
  doc.addEventListener('click', handler);
  doc.addEventListener('keydown', handler);
  return menu;
}
