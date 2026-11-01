/* features/listing.js — detail screen for ONE dataset listing, reached by deep link (/#/plot/<id>) or a chat card.
 * Data comes from the sanitised listing CSVs (no owner fields). Every interpolated value is escaped. */
import { nav } from '../app/router.js';
import { addRecent } from '../core/cookies.js';
import { escapeHtml } from '../core/html.js';
import { ownerState } from '../state/store.js';

const money = (v) => 'PKR ' + Math.round(v).toLocaleString('en-US');
const field = (label, value) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value == null || value === '' ? 'Not recorded' : String(value))}</dd></div>`;
const shell = (inner) => `<main class="listing"><button class="btn btn-outline" type="button" data-onclick="nav('home')">← Back to home</button>${inner}</main>`;

/** @param {string|null} id Property ID from the URL hash (already restricted to [A-Za-z0-9-]). */
export function renderListing(id) {
  const store = ownerState.store;
  if (ownerState.error) return shell(`<div class="owner-data-error" role="alert">${escapeHtml(ownerState.error)} <button class="btn btn-outline" type="button" data-onclick="loadOwnerVerificationData(true)">Retry</button></div>`);
  if (!store) return shell('<p role="status">Loading listing…</p>');
  const rec = store.lookup(id);
  if (!rec) return shell(`<h1>Listing not found</h1><p>No listing with ID <strong>${escapeHtml(id || '')}</strong> exists in the property records.</p>`);
  addRecent(rec.propertyId); // feeds the chat's "continue with…" chip (needs Preferences consent; otherwise this visit only)
  const est = rec.price == null ? store.estimate(rec) : null;
  const priceBlock = rec.price == null
    ? `<div class="listing-price">Not priced</div><p class="listing-note">Dataset estimate for similar listings (${escapeHtml(est.label)}, ${est.supportCount.toLocaleString()} records): about ${money(est.price)}. Indicative only.</p>`
    : `<div class="listing-price">${money(rec.price)}</div>`;
  return shell(`
    <h1>${escapeHtml(rec.propertyType)} in ${escapeHtml(rec.area)}${rec.block ? ', Block ' + escapeHtml(rec.block) : ''}</h1>
    <p class="listing-note">${escapeHtml(rec.propertyId)} · Demo data, not a real offer.</p>
    ${priceBlock}
    <dl class="listing-grid">
      ${field('Property type', rec.propertyType)}${field('Area', rec.area)}${field('Block', rec.block)}
      ${field('House number', rec.houseNumber)}${field('Street', rec.streetNumber)}${field('Rooms', rec.rooms)}
      ${field('Ownership status', rec.ownershipStatus)}${field('Legal check', rec.legalCheck)}
      ${field('Taxes', rec.taxesStatus)}${field('Utilities bill', rec.utilitiesBill)}
    </dl>
    <div class="listing-actions">
      <button class="btn btn-primary" type="button" data-onclick="openChat()">Ask the assistant</button>
      <button class="btn btn-outline" type="button" data-onclick="openOwnerCheck('${escapeHtml(rec.propertyId)}')">Check an owner name</button>
      <button class="btn btn-outline" type="button" data-onclick="openVerifyDocument()">Verify a document</button>
    </div>
    <p class="listing-note">Status fields are read from the dataset and are indicative, not proof. Owner names are never shown.</p>`);
}

/** Open Owner Verification with this listing already looked up. */
export function openOwnerCheck(id) {
  ownerState.id = String(id || '');
  ownerState.result = ownerState.store ? ownerState.store.lookup(ownerState.id) : null;
  ownerState.claim = ''; ownerState.check = null; ownerState.forecastYears = ''; ownerState.lookupError = '';
  nav('ownerverify');
}
