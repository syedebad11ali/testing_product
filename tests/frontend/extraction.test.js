import assert from 'node:assert';
import { test } from 'node:test';
import E from '../../frontend/js/domain/extraction.js';

/* =========================================================
   1. Real-world text layout variants
   ========================================================= */
test('colon+comma layout', ()=>{
  const t = 'Name: Demo Person Alpha, Plot No: 34-C, CNIC: 00000-0000101-0';
  const r = E.parseDocumentText(t);
  assert.strictEqual(r.ownerName.display, 'Demo Person Alpha');
  assert.strictEqual(r.plotNumber.display, '34-C');
  assert.strictEqual(r.cnic.display, '00000-0000101-0');
});

test('no punctuation, single-space layout', ()=>{
  const t = 'Name Demo Person Alpha Plot No 34-C CNIC 00000-0000101-0';
  const r = E.parseDocumentText(t);
  assert.strictEqual(r.ownerName.display, 'Demo Person Alpha');
  assert.strictEqual(r.plotNumber.display, '34-C');
  assert.strictEqual(r.cnic.display, '00000-0000101-0');
});

test('multiple spaces between label and value', ()=>{
  const t = 'Name:      Demo Person Alpha\nPlot No:      34-C\nCNIC:      00000-0000101-0';
  const r = E.parseDocumentText(t);
  assert.strictEqual(r.ownerName.display, 'Demo Person Alpha');
  assert.strictEqual(r.plotNumber.display, '34-C');
  assert.strictEqual(r.cnic.display, '00000-0000101-0');
});

test('tabs as separators', ()=>{
  const t = 'Name:\tDemo Person Alpha\nPlot No:\t34-C\nCNIC:\t00000-0000101-0';
  const r = E.parseDocumentText(t);
  assert.strictEqual(r.ownerName.display, 'Demo Person Alpha');
  assert.strictEqual(r.plotNumber.display, '34-C');
});

test('hash and dot separators', ()=>{
  const t = 'Plot #34-C\nName. Demo Person Alpha';
  const r = E.parseDocumentText(t);
  assert.strictEqual(r.plotNumber.display, '34-C');
  assert.strictEqual(r.ownerName.display, 'Demo Person Alpha');
});

test('labels on separate lines from values', ()=>{
  const t = 'Name\nDemo Person Alpha\nPlot No\n34-C\nCNIC\n00000-0000101-0';
  const r = E.parseDocumentText(t);
  assert.strictEqual(r.ownerName.display, 'Demo Person Alpha');
  assert.strictEqual(r.plotNumber.display, '34-C');
  assert.strictEqual(r.cnic.display, '00000-0000101-0');
});

test('different capitalization', ()=>{
  const t = 'NAME: demo person alpha\nplot no: 34-c\nCnIc: 00000-0000101-0';
  const r = E.parseDocumentText(t);
  assert.strictEqual(r.ownerName.display, 'demo person alpha');
  assert.strictEqual(r.plotNumber.display, '34-C'); // normalized uppercase
  assert.strictEqual(r.cnic.display, '00000-0000101-0');
});

test('extra whitespace / blank lines around fields', ()=>{
  const t = '\n\n   Name:   Demo Person Alpha   \n\n\n   Plot No:  34-C  \n\n';
  const r = E.parseDocumentText(t);
  assert.strictEqual(r.ownerName.display, 'Demo Person Alpha');
  assert.strictEqual(r.plotNumber.display, '34-C');
});

test('Urdu/English mixed text — English labels still parsed', ()=>{
  const t = 'یہ دستاویز ہے\nName: Demo Person Alpha\nپلاٹ نمبر\nPlot No: 34-C\nCNIC: 00000-0000101-0';
  const r = E.parseDocumentText(t);
  assert.strictEqual(r.ownerName.display, 'Demo Person Alpha');
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
  const good = E.extractCNIC('cnicnumber: 00000-0000101-0');
  assert.strictEqual(good.found, true);
  assert.strictEqual(good.display, '00000-0000101-0');
  const bad = E.extractCNIC('cnicnumber of the applicant was left blank on the form');
  assert.strictEqual(bad.found, false); // label-shaped text but no CNIC-shaped value follows
});

/* =========================================================
   3. Field boundaries (one field must not swallow the next)
   ========================================================= */
test('field does not consume the next field on one line', ()=>{
  const t = 'Name: Demo Person Alpha, Plot No: 34-C, CNIC: 00000-0000101-0';
  const r = E.parseDocumentText(t);
  assert.strictEqual(r.ownerName.display, 'Demo Person Alpha');
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
  const t = 'Name: Demo Person Alpha\nOwner Name: Bilal Khan';
  const r = E.extractOwnerName(t);
  assert.strictEqual(r.conflict, true);
});

test('two different CNICs -> conflict', ()=>{
  const t = 'CNIC: 00000-0000101-0\nCNIC: 00000-0000202-0';
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
  const t = 'Name: Demo Person Alpha\nName: Demo Person Alpha';
  const r = E.extractOwnerName(t);
  assert.strictEqual(r.conflict, false);
  assert.strictEqual(r.occurrenceCount, 2);
});

/* v2: "OWNER" is a distinct semantic ROLE (used directly by Property
   Papers, Building Approval, Property Tax), not a generic synonym for a
   bare "NAME" label — this is a deliberate change driven by the real
   sample-document evidence (see extraction.js header comment / README). */
test('v2: OWNER and bare NAME are tracked as separate roles, not merged', ()=>{
  const t = 'Owner: Demo Person Alpha\nName: Bilal Hassan';
  const byRole = E.extractByRole(t, 'name');
  assert.strictEqual(byRole.owner.display, 'Demo Person Alpha');
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
  const r = E.extractCNIC('CNIC: 000OO-0000I0I-0'); // I->1, O->0 within the token
  assert.strictEqual(r.found, true);
  assert.strictEqual(r.display, '00000-0000101-0');
});

test('missing hyphens in CNIC still recognized', ()=>{
  const r = E.extractCNIC('CNIC: 0000000001010');
  assert.strictEqual(r.found, true);
  assert.strictEqual(r.display, '00000-0000101-0');
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
  assert.strictEqual(E.detectDocumentType('Name: Demo Person Alpha, Plot No: 34-C').type, 'Unable to Determine');
});
test('empty text -> Unable to Determine', ()=>{
  assert.strictEqual(E.detectDocumentType('').type, 'Unable to Determine');
});

/* =========================================================
   Property matching / comparison
   ========================================================= */
const PROPS = [
  {id: 'p1', owner: 'Demo Person Alpha', plot: '34-C', cnic: '00000-0000101-0'},
  {id: 'p2', owner: 'Bilal Khan', plot: '52-A', cnic: '00000-0000201-0'}
];

test('matchProperty finds correct property on full match', ()=>{
  const extracted = E.parseDocumentText('Name: Demo Person Alpha, Plot No: 34-C, CNIC: 00000-0000101-0');
  const m = E.matchProperty(extracted, PROPS);
  assert.strictEqual(m.property.id, 'p1');
});

test('compareToProperty reports all matches for a fully matching document', ()=>{
  const extracted = E.parseDocumentText('Name: Demo Person Alpha, Plot No: 34-C, CNIC: 00000-0000101-0');
  const cmp = E.compareToProperty(extracted, PROPS[0]);
  assert.strictEqual(cmp.name, 'match');
  assert.strictEqual(cmp.plot, 'match');
  assert.strictEqual(cmp.cnic, 'match');
});

test('compareToProperty reports plot mismatch when plot differs', ()=>{
  const extracted = E.parseDocumentText('Name: Demo Person Alpha, Plot No: 52-A, CNIC: 00000-0000101-0');
  const cmp = E.compareToProperty(extracted, PROPS[0]);
  assert.strictEqual(cmp.name, 'match');
  assert.strictEqual(cmp.plot, 'mismatch');
  assert.strictEqual(cmp.cnic, 'match');
});

test('compareToProperty reports conflict state distinctly from mismatch', ()=>{
  const extracted = E.parseDocumentText('Plot No: 34-C\nPlot: 52-A\nName: Demo Person Alpha\nCNIC: 00000-0000101-0');
  const cmp = E.compareToProperty(extracted, PROPS[0]);
  assert.strictEqual(cmp.plot, 'conflict');
});

