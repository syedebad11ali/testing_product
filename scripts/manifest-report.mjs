/* Prints the full manifest-driven validation table (report only, never fails).
   Run: node scripts/manifest-report.mjs   — gating assertions live in tests/frontend/pipeline.test.js */
/* ==================================================================
   MANIFEST-DRIVEN VALIDATION AGAINST THE REAL SYNTHETIC DATASET
   Reads the REAL text captured from the sample documents:
     - tests/fixtures/ocr_text/*.txt   -> real `tesseract --psm 3` output
     - tests/fixtures/pdf_text/*.txt   -> real `pdftotext -layout` output
   and runs the actual extraction.js + property-comparison logic against
   it, then checks the result against tests/fixtures/manifest.json.

   This deliberately tests TWO separate things, per the task's own
   instruction to not conflate them:
     1. PARSER CORRECTNESS, isolated from OCR noise -> the PDF lane
        (pdftotext gives a clean embedded text layer for these generated
        PDFs, so PDF results measure extraction.js on its own).
     2. REAL OCR ACCURACY -> the PNG/JPG lane (tesseract output, with all
        of its real misreads: 0/9 confusion, "C" -> "€", dropped rows,
        etc.), which measures the full pipeline including OCR noise.

   Every document is compared TWO ways:
     (a) ANCHORED: compared directly against the property the manifest
         says it belongs to (property_id) — this isolates "did
         extraction + comparison correctly judge this document" from
         "did free-search find the right property in the whole DB".
     (b) FREE-SEARCH: run through Extraction.matchProperty() the same
         way the live app's context-free "Verify Your Document" flow
         does, searching across the whole database with no anchor.
   Where these two disagree, that's flagged explicitly rather than
   silently picking whichever one "passes".
   ================================================================== */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import E from '../frontend/js/domain/extraction.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(__dirname, '..');
const FIX = path.join(ROOT, 'tests', 'fixtures');
const manifest = JSON.parse(fs.readFileSync(path.join(FIX, 'manifest.json')));
const rawDb = JSON.parse(fs.readFileSync(path.join(FIX, 'property_database.json')));

// property_database.json keys are A/B/C; adapt to {owner,plot,cnic,survey,address,size} keyed by property_id.
const PROPERTIES = Object.values(rawDb).map(p => ({
  id: p.property_id, owner: p.owner, cnic: p.cnic, plot: p.plot, survey: p.survey, address: p.address, size: p.size
}));
const byId = {}; PROPERTIES.forEach(p => byId[p.id] = p);

// manifest "type" strings -> our TYPE_PROFILES keys
const TYPE_KEY = {
  'CNIC':'cnic', 'Property Ownership Paper':'property', 'Sale Deed':'sale_deed', 'Lease Deed':'lease_deed',
  'Allotment Letter':'allotment', 'Transfer Order':'transfer_order', 'NOC':'noc', 'Power of Attorney':'poa',
  'Building Approval':'building_approval', 'Property Tax Document':'property_tax', 'Utility Bill':'utility'
};
function typeKeyFor(entry){
  if(TYPE_KEY[entry.type]) return TYPE_KEY[entry.type];
  // the "altered_*" / "ocr_challenge" entries use descriptive types, not the plain 11 — all built on the Property Ownership Paper template
  return 'property';
}

// Manifest wording -> our status vocabulary (documented mapping, not silently forced)
function normalizeExpected(str){
  const s = str.toUpperCase();
  if(s.includes('INTERNAL CONFLICT')) return 'suspicious';
  if(s.includes('INSUFFICIENT') || s.includes('UNABLE TO VERIFY')) return 'unable_to_verify';
  if(s.includes('NOT VERIFIED')) return 'not_verified';
  if(s.includes('VERIFIED')) return 'verified'; // catches "VERIFIED" and "VERIFIED (if OCR succeeds)"
  return 'unknown';
}

const decide = (extraction, anchor, lane) => E.decide(extraction, anchor, {ocr: lane==='ocr'});

function loadText(baseName, lane){
  const file = path.join(FIX, lane==='ocr' ? 'ocr_text' : 'pdf_text', baseName + '.txt');
  return fs.existsSync(file) ? fs.readFileSync(file, 'utf8') : null;
}

function runLane(lane){
  const rows = [];
  manifest.forEach(entry => {
    const baseName = entry.file.replace(/\.(png|jpg)\/\.pdf$/i, '').replace(/\.jpg$/i,'');
    const text = loadText(baseName, lane);
    if(text === null) return; // e.g. ocr_challenge has no PDF counterpart
    const typeKey = typeKeyFor(entry);
    const extraction = E.parseDocumentText(text, typeKey);
    const anchor = byId[entry.property_id];
    const decision = decide(extraction, anchor, lane);
    const expected = normalizeExpected(entry.expected_result);
    const freeMatch = E.matchProperty(extraction, PROPERTIES);

    rows.push({
      file: baseName, lane, type: entry.type, expected, actual: decision.status,
      pass: expected === decision.status,
      reasons: decision.reasons,
      extractedName: extraction.ownerName.display, extractedPlot: extraction.plotNumber.display, extractedCnic: extraction.cnic.display,
      expectedOwner: entry.expected_owner, expectedPlot: entry.expected_plot, expectedCnic: entry.expected_cnic,
      freeMatchId: freeMatch.property ? freeMatch.property.id : null, anchorId: entry.property_id
    });
  });
  return rows;
}

const ocrRows = runLane('ocr');
const pdfRows = runLane('pdf');

function printTable(rows, title){
  console.log('\n=== '+title+' ('+rows.length+' documents) ===');
  console.log('File'.padEnd(28)+'Expected'.padEnd(18)+'Actual'.padEnd(18)+'Pass'.padEnd(6)+'Main issue');
  rows.forEach(r=>{
    const issue = r.pass ? '' : (r.reasons[0] || 'status mismatch');
    console.log(r.file.padEnd(28)+r.expected.padEnd(18)+r.actual.padEnd(18)+(r.pass?'PASS':'FAIL').padEnd(6)+issue);
  });
  const passN = rows.filter(r=>r.pass).length;
  console.log('-> '+passN+'/'+rows.length+' passed');
  return passN;
}

const ocrPass = printTable(ocrRows, 'PNG/JPG lane (real Tesseract OCR)');
const pdfPass = printTable(pdfRows, 'PDF lane (real pdftotext, clean text layer)');

console.log('\n=== Field-level extraction accuracy (PDF lane, clean-text baseline) ===');
console.log('File'.padEnd(28)+'Name'.padEnd(8)+'Plot'.padEnd(8)+'CNIC'.padEnd(8)+'Result');
pdfRows.forEach(r=>{
  const nameOk = r.extractedName && E.docNormalizeKey(r.extractedName)===E.docNormalizeKey(r.expectedOwner) ? 'match' : (r.extractedName?'diff':'—');
  const plotOk = r.extractedPlot ? (E.docNormalizeKey(r.expectedPlot).indexOf(E.docNormalizeKey(r.extractedPlot))!==-1 || E.docNormalizeKey(r.extractedPlot).indexOf(E.docNormalizeKey(r.expectedPlot))!==-1 ? 'match':'diff') : '—';
  const cnicOk = r.extractedCnic ? (r.extractedCnic.replace(/[^\d]/g,'')===r.expectedCnic.replace(/[^\d]/g,'') ? 'match':'diff') : '—';
  console.log(r.file.padEnd(28)+nameOk.padEnd(8)+plotOk.padEnd(8)+cnicOk.padEnd(8)+(r.pass?'PASS':'FAIL'));
});

console.log('\n=== Free-search vs anchored-property agreement ===');
[...ocrRows, ...pdfRows].forEach(r=>{
  if(r.freeMatchId && r.freeMatchId !== r.anchorId){
    console.log(r.lane+'/'+r.file+': anchored to '+r.anchorId+' but free-search matched '+r.freeMatchId+' instead');
  }
});

console.log('\nSUMMARY: OCR lane '+ocrPass+'/'+ocrRows.length+' | PDF lane '+pdfPass+'/'+pdfRows.length);

const outDir = path.join(ROOT, 'tests', '.results');
fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(path.join(outDir, 'manifest_results.json'), JSON.stringify({ocrRows, pdfRows}, null, 2));
process.exit(0); // this harness reports; it does not gate on pass/fail (that's for the written report to interpret)
