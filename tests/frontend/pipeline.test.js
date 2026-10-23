/* Drives the REAL app-level verification pipeline (domain/documentVerification.buildAutomaticResult)
 * over the captured OCR / pdftotext fixtures with free-search matching, exactly as the live
 * "Verify Your Document" flow does.
 *
 * These numbers are a REGRESSION BASELINE recorded from the pre-refactor code, not a quality
 * target. The listed false positives are a KNOWN ACCURACY PROBLEM (mismatching documents
 * reported as verified) — see docs/KNOWN_ISSUES.md. If you improve the matcher, update the
 * constants below in the same commit. */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import Extraction from '../../frontend/js/domain/extraction.js';
import { buildAutomaticResult } from '../../frontend/js/domain/documentVerification.js';

const FIX = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'fixtures');
const manifest = JSON.parse(fs.readFileSync(path.join(FIX, 'manifest.json'), 'utf8'));
const TYPE = { 'CNIC': 'cnic', 'Property Ownership Paper': 'property', 'Sale Deed': 'sale_deed', 'Lease Deed': 'lease_deed', 'Allotment Letter': 'allotment', 'Transfer Order': 'transfer_order', 'NOC': 'noc', 'Power of Attorney': 'poa', 'Building Approval': 'building_approval', 'Property Tax Document': 'property_tax', 'Utility Bill': 'utility' };
const normalize = (s) => { s = s.toUpperCase(); return s.includes('INTERNAL') ? 'suspicious' : (s.includes('INSUFFICIENT') || s.includes('UNABLE')) ? 'unable_to_verify' : s.includes('NOT VERIFIED') ? 'not_verified' : 'verified'; };

function runLanes() {
  const out = { ocr: [0, 0], pdf: [0, 0] }, falsePositives = [], falseNegatives = [];
  for (const entry of manifest) {
    const base = entry.file.replace(/\.(png|jpg)\/\.pdf$/i, '').replace(/\.jpg$/i, '');
    for (const [lane, dir, src] of [['ocr', 'ocr_text', 'ocr'], ['pdf', 'pdf_text', 'pdf-text']]) {
      const file = path.join(FIX, dir, base + '.txt');
      if (!fs.existsSync(file)) continue;
      const extraction = Extraction.parseDocumentText(fs.readFileSync(file, 'utf8'), TYPE[entry.type] || 'property');
      const result = buildAutomaticResult(extraction, { name: base }, src);
      const expected = normalize(entry.expected_result);
      out[lane][1]++;
      if (result.status === expected) out[lane][0]++;
      if (expected !== 'verified' && result.status === 'verified') falsePositives.push(`${lane}/${base}`);
      if (expected === 'verified' && result.status !== 'verified') falseNegatives.push(`${lane}/${base} -> ${result.status}`);
    }
  }
  return { out, falsePositives, falseNegatives };
}
const r = runLanes();

test('app-level pass counts match the recorded baseline', () => {
  assert.deepEqual(r.out, { ocr: [16, 29], pdf: [26, 28] });
});

test('KNOWN ISSUE: mismatching documents wrongly reported as verified (baseline)', () => {
  assert.deepEqual(r.falsePositives.sort(), ['ocr/power_of_attorney_mismatch', 'pdf/altered_multiple_mismatch', 'pdf/power_of_attorney_mismatch']);
});

test('valid documents not verified are limited to the recorded OCR cases', () => {
  assert.deepEqual(r.falseNegatives.sort(), [
    'ocr/allotment_matching -> unable_to_verify', 'ocr/ocr_challenge -> unable_to_verify',
    'ocr/power_of_attorney_matching -> unable_to_verify', 'ocr/sale_deed_matching -> unable_to_verify',
    'ocr/transfer_order_matching -> unable_to_verify']);
});

test('buildAutomaticResult never throws on empty OCR text', () => {
  const result = buildAutomaticResult(Extraction.parseDocumentText('', 'other'), { name: 'blank' }, 'ocr');
  assert.equal(result.status, 'unable_to_verify');
});
