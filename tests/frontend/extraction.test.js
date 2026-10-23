import assert from 'node:assert';
import { test } from 'node:test';
import E from '../../frontend/js/domain/extraction.js';

/* =========================================================
   1. Real-world text layout variants
   ========================================================= */
test('colon+comma layout', ()=>{
  const t = 'Name: Ahmed Ali, Plot No: 34-C, CNIC: 42101-1234567-1';
  const r = E.parseDocumentText(t);
  assert.strictEqual(r.ownerName.display, 'Ahmed Ali');
  assert.strictEqual(r.plotNumber.display, '34-C');
  assert.strictEqual(r.cnic.display, '42101-1234567-1');
});

test('no punctuation, single-space layout', ()=>{
  const t = 'Name Ahmed Ali Plot No 34-C CNIC 42101-1234567-1';
  const r = E.parseDocumentText(t);
  assert.strictEqual(r.ownerName.display, 'Ahmed Ali');
  assert.strictEqual(r.plotNumber.display, '34-C');
  assert.strictEqual(r.cnic.display, '42101-1234567-1');
});

test('multiple spaces between label and value', ()=>{
  const t = 'Name:      Ahmed Ali\nPlot No:      34-C\nCNIC:      42101-1234567-1';
  const r = E.parseDocumentText(t);
  assert.strictEqual(r.ownerName.display, 'Ahmed Ali');
  assert.strictEqual(r.plotNumber.display, '34-C');
  assert.strictEqual(r.cnic.display, '42101-1234567-1');
});

test('tabs as separators', ()=>{
  const t = 'Name:\tAhmed Ali\nPlot No:\t34-C\nCNIC:\t42101-1234567-1';
  const r = E.parseDocumentText(t);
  assert.strictEqual(r.ownerName.display, 'Ahmed Ali');
  assert.strictEqual(r.plotNumber.display, '34-C');
});

test('hash and dot separators', ()=>{
  const t = 'Plot #34-C\nName. Ahmed Ali';
  const r = E.parseDocumentText(t);
  assert.strictEqual(r.plotNumber.display, '34-C');
  assert.strictEqual(r.ownerName.display, 'Ahmed Ali');
});

test('labels on separate lines from values', ()=>{
  const t = 'Name\nAhmed Ali\nPlot No\n34-C\nCNIC\n42101-1234567-1';
  const r = E.parseDocumentText(t);
  assert.strictEqual(r.ownerName.display, 'Ahmed Ali');
  assert.strictEqual(r.plotNumber.display, '34-C');
  assert.strictEqual(r.cnic.display, '42101-1234567-1');
});

test('different capitalization', ()=>{
  const t = 'NAME: ahmed ali\nplot no: 34-c\nCnIc: 42101-1234567-1';
  const r = E.parseDocumentText(t);
  assert.strictEqual(r.ownerName.display, 'ahmed ali');
  assert.strictEqual(r.plotNumber.display, '34-C'); // normalized uppercase
  assert.strictEqual(r.cnic.display, '42101-1234567-1');
});

test('extra whitespace / blank lines around fields', ()=>{
  const t = '\n\n   Name:   Ahmed Ali   \n\n\n   Plot No:  34-C  \n\n';
  const r = E.parseDocumentText(t);
  assert.strictEqual(r.ownerName.display, 'Ahmed Ali');
  assert.strictEqual(r.plotNumber.display, '34-C');
});

test('Urdu/English mixed text — English labels still parsed', ()=>{
  const t = 'یہ دستاویز ہے\nName: Ahmed Ali\nپلاٹ نمبر\nPlot No: 34-C\nCNIC: 42101-1234567-1';
  const r = E.parseDocumentText(t);
  assert.strictEqual(r.ownerName.display, 'Ahmed Ali');
  assert.strictEqual(r.plotNumber.display, '34-C');
});

/* =========================================================
   2. False-positive label boundaries
   ========================================================= */
test('"nameplate" does not match name label', ()=>{
  const r = E.extractOwnerName('The nameplate on the gate was rusted.');
  assert.strictEqual(r.found, false);
});

test('"plotting" does not match plot label', ()=>{
  const r = E.extractPlotNumber('They were plotting a new subdivision.');
  assert.strictEqual(r.found, false);
});

test('"ownerless" does not match owner label', ()=>{
  const r = E.extractOwnerName('This is an ownerless stretch of land.');
  assert.strictEqual(r.found, false);
});

test('run-together "cnicnumber" only counts if value is CNIC-shaped', ()=>{
  const good = E.extractCNIC('cnicnumber: 42101-1234567-1');
  assert.strictEqual(good.found, true);
  assert.strictEqual(good.display, '42101-1234567-1');
  const bad = E.extractCNIC('cnicnumber of the applicant was left blank on the form');
  assert.strictEqual(bad.found, false); // label-shaped text but no CNIC-shaped value follows
});

/* =========================================================
   3. Field boundaries (one field must not swallow the next)
   ========================================================= */
test('field does not consume the next field on one line', ()=>{
  const t = 'Name: Ahmed Ali, Plot No: 34-C, CNIC: 42101-1234567-1';
  const r = E.parseDocumentText(t);
  assert.strictEqual(r.ownerName.display, 'Ahmed Ali');
  assert.ok(!/plot/i.test(r.ownerName.display));
  assert.ok(!/cnic/i.test(r.ownerName.display));
});

/* =========================================================
   4. Conflicts
   ========================================================= */
test('two different plot numbers -> conflict', ()=>{
  const t = 'Plot No: 34-C\n...\nPlot: 52-A';
  const r = E.extractPlotNumber(t);
  assert.strictEqual(r.conflict, true);
  assert.strictEqual(r.values.length, 2);
});

test('two different names -> conflict', ()=>{
  const t = 'Name: Ahmed Ali\nOwner Name: Bilal Khan';
  const r = E.extractOwnerName(t);
  assert.strictEqual(r.conflict, true);
});

test('two different CNICs -> conflict', ()=>{
  const t = 'CNIC: 42101-1234567-1\nCNIC: 42101-7654321-9';
  const r = E.extractCNIC(t);
  assert.strictEqual(r.conflict, true);
});

test('repeated identical value -> NOT a conflict', ()=>{
  const t = 'Plot No: 34-C\nPlot: 34-C';
  const r = E.extractPlotNumber(t);
  assert.strictEqual(r.conflict, false);
  assert.strictEqual(r.found, true);
  assert.strictEqual(r.display, '34-C');
  assert.strictEqual(r.occurrenceCount, 2);
});

test('one specific label + one generic label, same value -> not a conflict, not double counted oddly', ()=>{
  const t = 'Name: Ahmed Ali\nName: Ahmed Ali';
  const r = E.extractOwnerName(t);
  assert.strictEqual(r.conflict, false);
  assert.strictEqual(r.occurrenceCount, 2);
});

/* v2: "OWNER" is a distinct semantic ROLE (used directly by Property
   Papers, Building Approval, Property Tax), not a generic synonym for a
   bare "NAME" label — this is a deliberate change driven by the real
   sample-document evidence (see extraction.js header comment / README). */
test('v2: OWNER and bare NAME are tracked as separate roles, not merged', ()=>{
  const t = 'Owner: Ahmed Ali\nName: Bilal Hassan';
  const byRole = E.extractByRole(t, 'name');
  assert.strictEqual(byRole.owner.display, 'Ahmed Ali');
  assert.strictEqual(byRole.primary.display, 'Bilal Hassan');
});

test('one specific label + one generic label, different values -> conflict', ()=>{
  const t = 'Plot No: 34-C\nPlot: 52-A';
  const r = E.extractPlotNumber(t);
  assert.strictEqual(r.conflict, true);
  assert.strictEqual(r.values.length, 2);
});

/* =========================================================
   5. OCR noise
   ========================================================= */
test('O/0 and I/1 confusion inside CNIC is normalized', ()=>{
  const r = E.extractCNIC('CNIC: 42IOI-I234567-1'); // I->1, O->0 within the token
  assert.strictEqual(r.found, true);
  assert.strictEqual(r.display, '42101-1234567-1');
});

test('missing hyphens in CNIC still recognized', ()=>{
  const r = E.extractCNIC('CNIC: 4210112345671');
  assert.strictEqual(r.found, true);
  assert.strictEqual(r.display, '42101-1234567-1');
});

test('broken line / extra spaces does not create a false CNIC match', ()=>{
  const r = E.extractCNIC('CNIC:   \n   not available');
  assert.strictEqual(r.found, false);
});

test('slightly malformed label ("Plot No.") still parses', ()=>{
  const r = E.extractPlotNumber('Plot No. 34-C');
  assert.strictEqual(r.found, true);
  assert.strictEqual(r.display, '34-C');
});

test('garbage after a real label does not fabricate a plot number', ()=>{
  const r = E.extractPlotNumber('Plot No: ----');
  assert.strictEqual(r.found, false);
});

/* =========================================================
   6. document type detection
   ========================================================= */
test('detects Sale Deed', ()=>{
  assert.strictEqual(E.detectDocumentType('This Sale Deed is executed between...').type, 'Sale Deed');
});
test('detects Allotment Letter', ()=>{
  assert.strictEqual(E.detectDocumentType('Allotment Letter No. 445 issued by LDA').type, 'Allotment Letter');
});
test('unknown type when no keywords present', ()=>{
  assert.strictEqual(E.detectDocumentType('Name: Ahmed Ali, Plot No: 34-C').type, 'Unable to Determine');
});
test('empty text -> Unable to Determine', ()=>{
  assert.strictEqual(E.detectDocumentType('').type, 'Unable to Determine');
});

/* =========================================================
   Property matching / comparison
   ========================================================= */
const PROPS = [
  {id: 'p1', owner: 'Ahmed Ali', plot: '34-C', cnic: '42101-1234567-1'},
  {id: 'p2', owner: 'Bilal Khan', plot: '52-A', cnic: '42201-9876543-2'}
];

test('matchProperty finds correct property on full match', ()=>{
  const extracted = E.parseDocumentText('Name: Ahmed Ali, Plot No: 34-C, CNIC: 42101-1234567-1');
  const m = E.matchProperty(extracted, PROPS);
  assert.strictEqual(m.property.id, 'p1');
});

test('compareToProperty reports all matches for a fully matching document', ()=>{
  const extracted = E.parseDocumentText('Name: Ahmed Ali, Plot No: 34-C, CNIC: 42101-1234567-1');
  const cmp = E.compareToProperty(extracted, PROPS[0]);
  assert.strictEqual(cmp.name, 'match');
  assert.strictEqual(cmp.plot, 'match');
  assert.strictEqual(cmp.cnic, 'match');
});

test('compareToProperty reports plot mismatch when plot differs', ()=>{
  const extracted = E.parseDocumentText('Name: Ahmed Ali, Plot No: 52-A, CNIC: 42101-1234567-1');
  const cmp = E.compareToProperty(extracted, PROPS[0]);
  assert.strictEqual(cmp.name, 'match');
  assert.strictEqual(cmp.plot, 'mismatch');
  assert.strictEqual(cmp.cnic, 'match');
});

test('compareToProperty reports conflict state distinctly from mismatch', ()=>{
  const extracted = E.parseDocumentText('Plot No: 34-C\nPlot: 52-A\nName: Ahmed Ali\nCNIC: 42101-1234567-1');
  const cmp = E.compareToProperty(extracted, PROPS[0]);
  assert.strictEqual(cmp.plot, 'conflict');
});

