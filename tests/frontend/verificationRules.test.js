/* Regression tests for the document-verification false positives (Phase B).
 *
 * Each test asserts the actual STATUS and the decision REASONS produced by the real pipeline
 * (domain/extraction.js decide() + domain/documentVerification.js buildAutomaticResult()), not just that
 * the code runs. Inputs are the captured pdftotext / tesseract fixtures, sometimes with one value edited
 * so that a single failure mode is isolated.
 *
 * These are SYNTHETIC tests on fictional demo records. They show the decision rules behave as specified;
 * they say nothing about accuracy on real-world scans (see docs/KNOWN_ISSUES.md). */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import Extraction from '../../frontend/js/domain/extraction.js';
import { buildAutomaticResult } from '../../frontend/js/domain/documentVerification.js';

const FIX = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'fixtures');
const read = (lane, base) => fs.readFileSync(path.join(FIX, lane === 'ocr' ? 'ocr_text' : 'pdf_text', base + '.txt'), 'utf8');
const SRC = { ocr: 'ocr', pdf: 'pdf-text' };

/** Runs the full app-level pipeline over (optionally edited) fixture text. */
function run(lane, base, type, edit) {
  let text = read(lane, base);
  if (edit) text = edit(text);
  return buildAutomaticResult(Extraction.parseDocumentText(text, type), { name: base }, SRC[lane]);
}
/** Replaces `from` with `to` and fails loudly if the fixture text no longer contains `from` (guards the edit itself). */
const swap = (from, to) => (text) => { assert.ok(text.includes(from), `fixture no longer contains ${JSON.stringify(from)}`); return text.replace(from, to); };
const allReasons = (r) => (r.reasons || []).join(' | ');

/* ---- 1. Known mismatches that used to be reported as verified -------------------------------------------- */

for (const lane of ['pdf', 'ocr']) {
  test(`${lane}: power_of_attorney_mismatch is not verified (attorney name paired with a CNIC registered to someone else)`, () => {
    const r = run(lane, 'power_of_attorney_mismatch', 'poa');
    assert.equal(r.status, 'not_verified');
    assert.match(allReasons(r), /attorney/i);
    assert.match(allReasons(r), /CNIC/);
    // Privacy: the reason must not disclose who the CNIC is registered to.
    assert.doesNotMatch(allReasons(r), /Bilal Hassan/);
  });
}

test('pdf: altered_multiple_mismatch is not verified (owner/CNIC/plot swapped to another record, survey and address still describe the original)', () => {
  const r = run('pdf', 'altered_multiple_mismatch', 'property');
  assert.equal(r.status, 'not_verified');
  assert.match(allReasons(r), /[Ss]urvey/);
  assert.match(allReasons(r), /address/i);
});

test('ocr: altered_multiple_mismatch is never reported as verified', () => {
  assert.notEqual(run('ocr', 'altered_multiple_mismatch', 'property').status, 'verified');
});

/* ---- 2. Correctly matching documents stay verified ------------------------------------------------------- */

test('pdf: power_of_attorney_matching is still verified, and the limitation about the attorney is kept', () => {
  const r = run('pdf', 'power_of_attorney_matching', 'poa');
  assert.equal(r.status, 'verified');
  assert.ok(r.limitations.some((l) => /attorney/i.test(l)));
});

test('pdf: every *_matching fixture is still verified', () => {
  const TYPES = { cnic: 'cnic', property: 'property', sale_deed: 'sale_deed', lease_deed: 'lease_deed', allotment: 'allotment', transfer_order: 'transfer_order', noc: 'noc', power_of_attorney: 'poa', building_approval: 'building_approval', property_tax: 'property_tax', utility: 'utility' };
  const names = fs.readdirSync(path.join(FIX, 'pdf_text')).filter((f) => f.endsWith('_matching.txt')).map((f) => f.replace('.txt', ''));
  assert.equal(names.length, 11);
  for (const base of names) {
    const type = TYPES[base.replace('_matching', '')];
    assert.ok(type, base);
    assert.equal(run('pdf', base, type).status, 'verified', base);
  }
});

/* ---- 3. Party identity cross-check (generic, not attorney-specific) -------------------------------------- */

test('an attorney whose CNIC is on no record cannot be contradicted: stays verified but the attorney is declared unchecked', () => {
  const r = run('pdf', 'power_of_attorney_mismatch', 'poa', (t) => t.replace('00000-0000000-1', '00000-0000000-7'));
  assert.equal(r.status, 'verified');
  assert.ok(r.limitations.some((l) => /attorney/i.test(l)));
});

test('an attorney name matching the record that owns the attorney CNIC is accepted', () => {
  assert.equal(run('pdf', 'power_of_attorney_mismatch', 'poa', swap('Zubair Khan', 'Bilal Hassan')).status, 'verified');
});

test('an attorney CNIC that belongs to a different record owner than the stated attorney name is not verified', () => {
  const r = run('pdf', 'power_of_attorney_matching', 'poa', swap('00000-0000000-1', '00000-0000000-2'));
  assert.equal(r.status, 'not_verified');
});

/* ---- 4. Partial extraction must not count as a match ----------------------------------------------------- */

test('a truncated plot number ("4-C" for record "34-C") is a mismatch, not a match', () => {
  const r = run('pdf', 'property_matching', 'property', (t) => t.replace(/(PLOT NUMBER\s+)34-C/, '$14-C'));
  assert.notEqual(r.status, 'verified');
});

test('a plot number that is only a prefix ("34" for record "34-C") is not verified', () => {
  const r = run('pdf', 'property_matching', 'property', (t) => t.replace(/(PLOT NUMBER\s+)34-C/, '$134'));
  assert.notEqual(r.status, 'verified');
});

test('Extraction.compareToProperty: plot must match on a token boundary', () => {
  const rec = { owner: 'A B', plot: 'Plot 134-C, Street 12', cnic: '' };
  const ex = Extraction.parseDocumentText('NAME A B\nPLOT NUMBER 34-C\n', 'property');
  assert.equal(Extraction.compareToProperty(ex, rec).plot, 'mismatch');
  assert.equal(Extraction.compareToProperty(Extraction.parseDocumentText('NAME A B\nPLOT NUMBER 134-C\n', 'property'), rec).plot, 'match');
});

test('plot spacing/hyphen differences alone are still tolerated ("34C" vs "34-C")', () => {
  const rec = { owner: 'A B', plot: '34-C', cnic: '' };
  const ex = Extraction.parseDocumentText('NAME A B\nPLOT NUMBER 34C\n', 'property');
  assert.equal(Extraction.compareToProperty(ex, rec).plot, 'match');
});

/* ---- 5. Missing / unreadable / uncompared fields are never evidence of a match --------------------------- */

test('decide(): a required field that was found but cannot be compared (no CNIC on record) is unable_to_verify, not verified', () => {
  const rec = { id: 'X', owner: 'Ahmed Raza', plot: '34-C', cnic: '' };
  const ex = Extraction.parseDocumentText(read('pdf', 'property_matching'), 'property');
  const d = Extraction.decide(ex, rec, {});
  assert.equal(d.status, 'unable_to_verify');
  assert.match(d.reasons.join(' '), /CNIC/);
  assert.match(d.reasons.join(' '), /compared/i);
});

test('decide(): the same document is verified when the record can supply every required field', () => {
  const rec = { id: 'X', owner: 'Ahmed Raza', plot: '34-C', cnic: '00000-0000000-0' };
  const ex = Extraction.parseDocumentText(read('pdf', 'property_matching'), 'property');
  assert.equal(Extraction.decide(ex, rec, {}).status, 'verified');
});

test('decide(): an unreadable approved-area value is not treated as matching', () => {
  const rec = { id: 'X', owner: 'Ahmed Raza', plot: '34-C', cnic: '00000-0000000-0', size: '500 Sq. Yards' };
  const ex = Extraction.parseDocumentText(read('pdf', 'building_approval_matching'), 'building_approval');
  assert.equal(ex.approvedArea.found, true);
  ex.approvedArea = Object.assign({}, ex.approvedArea, { display: 'as per sanctioned plan', value: 'as per sanctioned plan' });
  const d = Extraction.decide(ex, rec, {});
  assert.notEqual(d.status, 'verified');
  assert.equal(d.cmp.approvedArea, 'unknown');
});

test('altered_missing_plot stays "unable to verify" in both lanes (a missing required field is never a match)', () => {
  for (const lane of ['pdf', 'ocr']) {
    const r = run(lane, 'altered_missing_plot', 'property');
    assert.equal(r.status, 'unable_to_verify', lane);
    assert.match(allReasons(r), /plot/i, lane);
  }
});

test('empty, whitespace and unreadable text are unable_to_verify', () => {
  for (const text of ['', '   \n  ', '@@## ~~ !!']) {
    const r = buildAutomaticResult(Extraction.parseDocumentText(text, 'property'), { name: 'x' }, 'ocr');
    assert.equal(r.status, 'unable_to_verify', JSON.stringify(text));
  }
});

/* ---- 6. Conflicting evidence ------------------------------------------------------------------------------ */

test('pdf: altered_conflicting_info is "suspicious" (the document contradicts itself)', () => {
  const r = run('pdf', 'altered_conflicting_info', 'property');
  assert.equal(r.status, 'suspicious');
  assert.match(allReasons(r), /more than one different value/);
});

test('a document with two different CNICs for the same party is suspicious, never verified', () => {
  const r = run('pdf', 'property_matching', 'property', (t) => t.replace(/(CNIC\s+)00000-0000000-0/, '$100000-0000000-0\n  CNIC                                       00000-0000000-5'));
  assert.notEqual(r.status, 'verified');
});

/* ---- 7. Whole-dataset invariants -------------------------------------------------------------------------- */

test('no fixture whose expected result is not "verified" is ever reported as verified (either lane)', () => {
  const manifest = JSON.parse(fs.readFileSync(path.join(FIX, 'manifest.json'), 'utf8'));
  const TYPE = { 'CNIC': 'cnic', 'Property Ownership Paper': 'property', 'Sale Deed': 'sale_deed', 'Lease Deed': 'lease_deed', 'Allotment Letter': 'allotment', 'Transfer Order': 'transfer_order', 'NOC': 'noc', 'Power of Attorney': 'poa', 'Building Approval': 'building_approval', 'Property Tax Document': 'property_tax', 'Utility Bill': 'utility' };
  const wrong = [];
  for (const e of manifest) {
    const base = e.file.replace(/\.(png|jpg)\/\.pdf$/i, '').replace(/\.jpg$/i, '');
    if (/^VERIFIED/.test(e.expected_result)) continue;
    for (const lane of ['pdf', 'ocr']) {
      if (!fs.existsSync(path.join(FIX, lane === 'ocr' ? 'ocr_text' : 'pdf_text', base + '.txt'))) continue;
      if (run(lane, base, TYPE[e.type] || 'property').status === 'verified') wrong.push(`${lane}/${base}`);
    }
  }
  assert.deepEqual(wrong, []);
});
