/* features/homePrefs.js — remember the Home screen's area / type / sort choice in `kpt_prefs`.
 * Cookie values are untrusted: they are only ever used to pick one of the options the page really offers
 * (case-insensitive match), never inserted into the page. Free-text search is not stored. Persistence happens
 * only with Preferences consent (core/cookies.js decides); without it the choice lasts for this visit. */
import { readPrefs, writePrefs } from '../core/cookies.js';

// UI sort values -> cookie codes (core/prefs.js SORTS). "Largest Property" has no code, so it is not remembered.
const SORT_TO_CODE = { newest: 'newest', low: 'price_asc', high: 'price_desc' };
const CODE_TO_SORT = Object.fromEntries(Object.entries(SORT_TO_CODE).map(([ui, code]) => [code, ui]));

const pick = (value, options) => (typeof value === 'string' ? options.find((o) => o.toLowerCase() === value.toLowerCase()) : undefined);

/** Pure: saved prefs + the options the page offers -> the filter state to start with. */
export function restoreFilters(prefs, areas, types) {
  const out = {};
  const area = pick(prefs && prefs.area, areas), type = pick(prefs && prefs.ptype, types);
  if (area) out.areaFilter = area;
  if (type) out.typeFilter = type;
  if (prefs && typeof prefs.sort === 'string' && Object.hasOwn(CODE_TO_SORT, prefs.sort)) out.sort = CODE_TO_SORT[prefs.sort];
  return out;
}

/** Pure: current filter state -> the prefs patch (null clears a key; the sanitiser drops it). */
export function filtersPatch(state) {
  return { area: state.areaFilter ? state.areaFilter.toLowerCase() : null, ptype: state.typeFilter ? state.typeFilter.toLowerCase() : null,
    sort: SORT_TO_CODE[state.sort] || null };
}

export function loadHomeFilters(state, areas, types) { Object.assign(state, restoreFilters(readPrefs(), areas, types)); }
export function saveHomeFilters(state) { writePrefs(filtersPatch(state)); }
