/* Phase B.1 review: regression tests for four defects found by probing the Phase B/B.1 code.
 *
 *   1. Approved-area comparison ignored units, so "1 Acre", "500 Sq. Meters" or "600 Sq. Yards" (against a record held in Sq. Ft.)
 *      could end "verified". Areas are now compared in square yards; a number without a recognised unit is "unknown".
 *   2. A full CNIC (the value read from the document) was written into reason text, shown on screen and stored unmasked.
 *   3. scripts/manifest-report.mjs decided against the manifest's own record while the app picks the record by free search,
 *      so the report could differ from the app. Both now call Extraction.verifyAgainstRecords().
 *   4. The manual-check result view rendered reasons without escaping (one reason quotes user-typed text).
 *
 * Synthetic fixtures on fictional demo records only: they show the rules behave as specified and say nothing about real scans. */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import Extraction from '../../frontend/js/domain/extraction.js';
import { buildAutomaticResult, allVerificationRecords } from '../../frontend/js/domain/documentVerification.js';
import { sanitizeResultForStorage, maskCnic } from '../../frontend/js/domain/resultPrivacy.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIX = path.join(HERE, '..', 'fixtures');
const read = (lane, base) => fs.readFileSync(path.join(FIX, lane === 'ocr' ? 'ocr_text' : 'pdf_text', base + '.txt'), 'utf8');
const SRC = { ocr: 'ocr', pdf: 'pdf-text' };
const swap = (from, to) => (text) => { assert.ok(text.includes(from), `fixture no longer contains ${JSON.stringify(from)}`); return text.replace(from, to); };
const FIXTURE_RECORDS = Object.values(JSON.parse(fs.readFileSync(path.join(FIX, 'property_database.json'), 'utf8')))
  .map((p) => ({ id: p.property_id, owner: p.owner, cnic: p.cnic, plot: p.plot, survey: p.survey, address: p.address, size: p.size }));
const rec = (over) => Object.assign({}, FIXTURE_RECORDS[0], over);                      // DEMO-KPT-001 (500 Sq. Yards) with edits
const approval = (area) => Extraction.parseDocumentText(swap('480 Sq. Yards', area)(read('pdf', 'building_approval_matching')), 'building_approval');

const TYPE = { 'CNIC': 'cnic', 'Property Ownership Paper': 'property', 'Sale Deed': 'sale_deed', 'Lease Deed': 'lease_deed', 'Allotment Letter': 'allotment', 'Transfer Order': 'transfer_order', 'NOC': 'noc', 'Power of Attorney': 'poa', 'Building Approval': 'building_approval', 'Property Tax Document': 'property_tax', 'Utility Bill': 'utility' };
const normalize = (s) => { s = s.toUpperCase(); return s.includes('INTERNAL') ? 'suspicious' : (s.includes('INSUFFICIENT') || s.includes('UNABLE')) ? 'unable_to_verify' : s.includes('NOT VERIFIED') ? 'not_verified' : s.includes('VERIFIED') ? 'verified' : 'unknown'; };
const manifest = JSON.parse(fs.readFileSync(path.join(FIX, 'manifest.json'), 'utf8'));
const rows = [];
for (const entry of manifest) {
  const base = entry.file.replace(/\.(png|jpg)\/\.pdf$/i, '').replace(/\.jpg$/i, '');
  for (const lane of ['ocr', 'pdf']) {
    const file = path.join(FIX, lane === 'ocr' ? 'ocr_text' : 'pdf_text', base + '.txt');
    if (fs.existsSync(file)) rows.push({ base, lane, expected: normalize(entry.expected_result), type: TYPE[entry.type] || 'property', text: fs.readFileSync(file, 'utf8') });
  }
}
const FULL_CNIC = /\b\d{5}-?\d{7}-?\d\b/;

/* ---- 1. area units ------------------------------------------------------------------------------------------------ */

test('areaInSqYards converts known units and returns NaN for anything it cannot be sure of', () => {
  const f = Extraction.areaInSqYards;
  assert.equal(f('480 Sq. Yards'), 480);
  assert.equal(f('1,200 sq yds'), 1200);
  assert.equal(f('4500 Sq. Ft.'), 500);
  assert.ok(Math.abs(f('100 Sq. Meters') - 119.599005) < 1e-6);
  assert.equal(f('1 Acre'), 4840);
  for (const unsure of ['480', '20 Marla', '5 Kanal', '480 gaz', 'Plot 12, 480 Sq. Yards', 'as per sanctioned plan', '', null, undefined]) {
    assert.ok(Number.isNaN(f(unsure)), `${JSON.stringify(unsure)} must not be comparable`);
  }
});

test('approved area: a larger area written in another unit is not verified (was "verified" before the fix)', () => {
  for (const area of ['500 Sq. Meters', '1 Acre', '0.2 Acre', '501 Sq. Yards', '4800 Sq. Ft.']) {
    const d = Extraction.decide(approval(area), rec(), {});
    assert.equal(d.status, 'not_verified', area);
    assert.match(d.reasons.join(' '), /approved area/i, area);
  }
});

test('approved area: a smaller or equal area still verifies, whichever supported unit is used', () => {
  for (const area of ['480 Sq. Yards', '500 Sq. Yards', '4500 Sq. Ft.', '480 Sq. Ft.', '100 Sq. Meters']) {
    assert.equal(Extraction.decide(approval(area), rec(), {}).status, 'verified', area);
  }
});

test('approved area: a number with no recognised unit is never a match', () => {
  for (const area of ['480', '20 Marla']) {
    const d = Extraction.decide(approval(area), rec(), {});
    assert.equal(d.status, 'unable_to_verify', area);
    assert.equal(d.cmp.approvedArea, 'unknown', area);
  }
});

test('approved area: the record may be in another unit; an unreadable record size cannot support a match', () => {
  const sqft = rec({ size: '4500 Sq. Ft.' });                              // = 500 Sq. Yards
  assert.equal(Extraction.decide(approval('600 Sq. Yards'), sqft, {}).status, 'not_verified');
  assert.equal(Extraction.decide(approval('480 Sq. Yards'), sqft, {}).status, 'verified');
  for (const size of ['500', '—', 'N/A', '500 Marla', undefined]) {
    const d = Extraction.decide(approval('480 Sq. Yards'), rec({ size }), {});
    assert.equal(d.status, 'unable_to_verify', JSON.stringify(size));
  }
});

test('approved area end to end (real app function and the app\'s own record set)', () => {
  const run = (area) => buildAutomaticResult(approval(area), { name: 'x' }, 'pdf-text');
  assert.equal(run('480 Sq. Yards').status, 'verified');
  assert.equal(run('1 Acre').status, 'not_verified');
  assert.equal(run('480').status, 'unable_to_verify');
});

/* ---- 2. full CNICs never appear in message text -------------------------------------------------------------------- */

test('maskCnic keeps only the first five and last two digits', () => {
  assert.equal(maskCnic('4210112345671'), '42101-******7-1');
});

test('an OCR-uncertain CNIC is shown masked in reasons, checks and limitations (three fixtures that misread it)', () => {
  for (const base of ['sale_deed_matching', 'transfer_order_matching', 'power_of_attorney_matching']) {
    const type = manifest.find((e) => e.file.startsWith(base))?.type;
    const r = buildAutomaticResult(Extraction.parseDocumentText(read('ocr', base), TYPE[type]), { name: base }, 'ocr');
    assert.equal(r.status, 'unable_to_verify', base);
    const text = JSON.stringify([r.reasons, r.checks, r.limitations]);
    assert.doesNotMatch(text, FULL_CNIC, `${base}: full CNIC in result text`);
    assert.match(r.reasons.join(' '), /CNIC read from the image \("\d{5}-\*{6}\d-\d"\)/, base);
  }
});

test('no result text for any fixture, in either lane, contains a full CNIC', () => {
  for (const row of rows) {
    const r = buildAutomaticResult(Extraction.parseDocumentText(row.text, row.type), { name: row.base }, SRC[row.lane]);
    assert.doesNotMatch(JSON.stringify([r.reasons, r.checks, r.limitations]), FULL_CNIC, `${row.lane}/${row.base}`);
  }
});

test('stored results mask CNICs in reasons and limitations too (it already did for checks)', () => {
  const stored = sanitizeResultForStorage({
    status: 'unable_to_verify', reasons: ['CNIC read from the image ("42101-1234567-1") differs', 'no CNIC here', 'bare 4210112345671 digits'],
    limitations: ['quoted 42101-1234567-1 once'], checks: [{ text: 'CNIC 42101-1234567-1' }],
  });
  for (const k of ['reasons', 'limitations']) assert.doesNotMatch(JSON.stringify(stored[k]), FULL_CNIC, k);
  assert.doesNotMatch(JSON.stringify(stored.checks), FULL_CNIC);
  assert.equal(stored.reasons[1], 'no CNIC here');
  assert.equal(stored.reasons[0], 'CNIC read from the image ("42101-******7-1") differs');
});

/* ---- 3. the report and the app use one decision path --------------------------------------------------------------- */

test('verifyAgainstRecords gives the same status as the app for every fixture in both lanes', () => {
  assert.ok(rows.length >= 57, 'fixtures were not found');
  for (const row of rows) {
    const ex = () => Extraction.parseDocumentText(row.text, row.type);
    const app = buildAutomaticResult(ex(), { name: row.base }, SRC[row.lane]).status;
    const shared = Extraction.verifyAgainstRecords(ex(), allVerificationRecords(), { ocr: row.lane === 'ocr' }).status;
    const report = Extraction.verifyAgainstRecords(ex(), FIXTURE_RECORDS, { ocr: row.lane === 'ocr' }).status;   // what manifest-report.mjs passes
    assert.equal(shared, app, `${row.lane}/${row.base}: shared function differs from the app`);
    assert.equal(report, app, `${row.lane}/${row.base}: report records differ from the app's records`);
  }
});

test('application path: nothing is verified unless the manifest expects "verified", and the PDF lane matches all 28', () => {
  const falsePositives = [], pdf = { pass: 0, total: 0 };
  for (const row of rows) {
    const r = buildAutomaticResult(Extraction.parseDocumentText(row.text, row.type), { name: row.base }, SRC[row.lane]);
    if (r.status === 'verified' && row.expected !== 'verified') falsePositives.push(`${row.lane}/${row.base}`);
    if (row.lane === 'pdf') { pdf.total++; if (r.status === row.expected) pdf.pass++; }
  }
  assert.deepEqual(falsePositives, []);
  assert.deepEqual(pdf, { pass: 28, total: 28 });
});

test('verifyAgainstRecords: nothing readable, no matching record, and self-contradicting documents', () => {
  const none = Extraction.verifyAgainstRecords(Extraction.parseDocumentText('hello world', 'property'), FIXTURE_RECORDS, {});
  assert.deepEqual([none.status, none.earlyExit, none.noMatch, none.matched], ['unable_to_verify', true, false, null]);

  const stranger = 'Owner: Zubair Qureshi\nCNIC: 42101-1234567-1\nPlot Number: 901-Z\n';
  const noMatch = Extraction.verifyAgainstRecords(Extraction.parseDocumentText(stranger, 'property'), FIXTURE_RECORDS, {});
  assert.deepEqual([noMatch.status, noMatch.earlyExit, noMatch.noMatch], ['not_verified', true, true]);

  const conflicting = Extraction.verifyAgainstRecords(Extraction.parseDocumentText(read('pdf', 'altered_conflicting_info'), 'property'), FIXTURE_RECORDS, { ocr: false });
  assert.equal(conflicting.status, 'suspicious');
  assert.equal(conflicting.earlyExit, false);
});

test('verifyAgainstRecords does not need the caller to pass records inside opts', () => {
  const ex = Extraction.parseDocumentText(read('pdf', 'power_of_attorney_mismatch'), 'poa');
  const d = Extraction.verifyAgainstRecords(ex, FIXTURE_RECORDS, { ocr: false });
  assert.notEqual(d.status, 'verified');                                        // the attorney cross-check needs the records
  assert.match(d.reasons.join(' '), /CNIC given for the attorney/i);
});

/* ---- 4. reasons are escaped when rendered (source check: the views build HTML strings and need a DOM to run) -------- */

test('every place that renders result reasons escapes them', () => {
  const src = fs.readFileSync(path.join(HERE, '..', '..', 'frontend', 'js', 'features', 'verifyDocument', 'views.js'), 'utf8');
  const lines = src.split('\n').map((l, i) => ({ l, n: i + 1 })).filter(({ l }) => /\.reasons\b[^\n]*\.map\(/.test(l) || /r\.reasons\.map\(/.test(l));
  assert.ok(lines.length >= 3, 'expected the reason renderers to be found');
  for (const { l, n } of lines) assert.match(l, /escapeHtml\(\s*x\s*\)/, `views.js:${n} renders a reason without escapeHtml`);
});
