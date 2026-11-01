/* Phase B.1 regression tests: placeholder/missing values, OCR-cautious names, no record values in reasons,
 * masked CNIC in stored history, and the result screen (no "Owner on record", limitations text).
 *
 * SYNTHETIC inputs on fictional demo records (DEMO-KPT-001 .. 003). They check that the decision rules behave as
 * specified; they say nothing about accuracy on real scans (docs/KNOWN_ISSUES.md). */
import test from 'node:test';
import assert from 'node:assert/strict';
import { installDom } from './helpers/domStub.js';

const { document } = installDom();
const Extraction = (await import('../../frontend/js/domain/extraction.js')).default;
const { buildAutomaticResult, sanitizeResultForStorage } = await import('../../frontend/js/domain/documentVerification.js');
const { DEMO_PROPERTIES } = await import('../../frontend/js/data/documentTypes.js');
const { render } = await import('../../frontend/js/app/router.js');
const { state, docState, resetDocState } = await import('../../frontend/js/state/store.js');

const REC = DEMO_PROPERTIES[0];            // Ahmed Raza, 00000-0000000-0, 34-C, SRV-TEST-001
const propDoc = (name, cnic, plot) => `PROPERTY RECORD\nOwner: ${name}\nCNIC: ${cnic}\nPlot: ${plot}\n`;
const decideProp = (text, record, ocr = false, type = 'property') =>
  Extraction.decide(Extraction.parseDocumentText(text, type), record, { ocr, records: [record] });
const RECORDED = (r) => [r.owner, r.cnic, r.cnic.replace(/-/g, ''), r.plot, r.survey, r.address, r.size];
/* A record value is only a leak if the document did not itself carry it (a matching field legitimately shows the document's own value). */
const leaks = (r, record, docText) => {
  const hay = JSON.stringify([r.reasons, r.checks, r.limitations, r.cmp && r.cmp.details]);
  return RECORDED(record).filter((v) => v && v !== '—' && !docText.includes(v) && hay.includes(v));
};

/* ---- 1. missing-value / placeholder handling ---------------------------------------------------------- */

test('isMissingValue treats blanks and placeholders as missing, real values as present', () => {
  for (const v of ['', '  ', '—', '–', '-', '--', 'N/A', 'n/a', 'N.A.', 'nil', 'None', 'null', 'unknown', 'TBD', 'Not available', 'not provided', 'No data', null, undefined]) {
    assert.equal(Extraction.isMissingValue(v), true, JSON.stringify(v));
  }
  for (const v of ['Ahmed Raza', '34-C', 'SRV-TEST-001', '00000-0000000-0', '0']) assert.equal(Extraction.isMissingValue(v), false, v);
});

for (const ph of ['—', '–', '-', 'N/A', 'nil', 'none', 'null', 'unknown', 'TBD', 'not available']) {
  test(`a document whose fields all read "${ph}" is unable_to_verify, never verified or a mismatch`, () => {
    const d = decideProp(propDoc(ph, ph, ph), REC);
    assert.equal(d.status, 'unable_to_verify');
  });
}

test('a placeholder name does not count as a detected name even when CNIC and plot are real', () => {
  const x = Extraction.parseDocumentText(propDoc('N/A', REC.cnic, REC.plot), 'property');
  assert.equal(x.ownerName.found, false);
  assert.equal(decideProp(propDoc('N/A', REC.cnic, REC.plot), REC).status, 'unable_to_verify');
});

test('a placeholder survey number in the document is not detected', () => {
  const x = Extraction.parseDocumentText('LEASE DEED\nLessor Name: Ahmed Raza\nCNIC: 00000-0000000-0\nPlot: 34-C\nSurvey No: —\n', 'lease_deed');
  assert.equal(x.surveyNumber.found, false);
});

test('a record whose survey/plot/owner is only a placeholder cannot produce a mismatch: the field stays unknown', () => {
  const bare = { id: 'T-1', owner: '—', cnic: '—', plot: 'N/A', survey: '—', address: 'TBD', size: '—' };
  const x = Extraction.parseDocumentText('LEASE DEED\nLessor Name: Ahmed Raza\nCNIC: 00000-0000000-0\nPlot: 34-C\nSurvey No: SRV-9\n', 'lease_deed');
  const c = Extraction.compareToProperty(x, bare, {});
  for (const f of ['name', 'cnic', 'plot', 'survey']) assert.equal(c[f], 'unknown', f);
  assert.deepEqual(c.mismatches, []);
  const d = Extraction.decide(x, bare, { records: [bare] });
  assert.equal(d.status, 'unable_to_verify');
});

test('a required field that is present but has no usable record value is unable_to_verify, not verified', () => {
  const noCnic = Object.assign({}, REC, { cnic: '—' });
  assert.equal(decideProp(propDoc(REC.owner, REC.cnic, REC.plot), noCnic).status, 'unable_to_verify');
  assert.equal(decideProp(propDoc(REC.owner, REC.cnic, REC.plot), REC).status, 'verified');
});

/* ---- 2. identifiers: whole-token matching ------------------------------------------------------------ */

test('a plot that is only a substring of the record plot is not verified (prefix, suffix, inner)', () => {
  for (const plot of ['4-C', '34', '-C', 'C']) {
    const d = decideProp(propDoc(REC.owner, REC.cnic, plot), REC);
    assert.notEqual(d.status, 'verified', plot);
  }
  const longer = Object.assign({}, REC, { plot: '134-C' });
  assert.equal(decideProp(propDoc(REC.owner, REC.cnic, '34-C'), longer).status, 'not_verified');
});

test('spacing and hyphen differences in the same plot still match ("34C" for "34-C")', () => {
  assert.equal(decideProp(propDoc(REC.owner, REC.cnic, '34C'), REC).status, 'verified');
});

/* ---- 3. names: PDF text layer is exact, OCR is cautious ---------------------------------------------- */

test('PDF text layer: a name one letter off is a definite mismatch', () => {
  assert.equal(decideProp(propDoc('Ahmed Raz4', REC.cnic, REC.plot), REC, false).status, 'not_verified');
});

test('OCR: a name one character off (or OCR-confusable) is unable_to_verify, never not_verified and never verified', () => {
  for (const name of ['Ahmed Raz4', 'Ahmed Raza1', 'Ahmcd Raza']) {
    const d = decideProp(propDoc(name, REC.cnic, REC.plot), REC, true);
    assert.equal(d.status, 'unable_to_verify', name);
    assert.deepEqual(d.cmp.mismatches, [], name);
    assert.equal(d.cmp.name, 'uncertain', name);
  }
});

test('OCR: a clearly different name is still a definite mismatch', () => {
  const d = decideProp(propDoc('Zubair Khan', REC.cnic, REC.plot), REC, true);
  assert.equal(d.status, 'not_verified');
});

test('OCR: short names are not fuzzy-matched (too little evidence either way)', () => {
  const short = Object.assign({}, REC, { owner: 'Ali Re' });
  assert.equal(decideProp(propDoc('Ali Ra', REC.cnic, REC.plot), short, true).status, 'not_verified');
});

test('OCR: an attorney name that only OCR-differs from the name on record for the attorney CNIC is not a proven contradiction', () => {
  const rec2 = DEMO_PROPERTIES[1];   // Bilal Hassan, 00000-0000000-1
  const text = 'POWER OF ATTORNEY\nPrincipal\nName: Ahmed Raza\nCNIC: 00000-0000000-0\nPlot: 34-C\nAttorney\nName: Bilal Hassan1\nCNIC: 00000-0000000-1\n';
  const x = Extraction.parseDocumentText(text, 'poa');
  const ocr = Extraction.decide(x, REC, { ocr: true, records: [REC, rec2] });
  assert.notEqual(ocr.status, 'not_verified');
  assert.notEqual(ocr.status, 'verified');
  const pdf = Extraction.decide(x, REC, { ocr: false, records: [REC, rec2] });
  assert.equal(pdf.status, 'not_verified');
});

/* ---- 4. contradictory information is never verified -------------------------------------------------- */

test('a clearly contradictory attorney CNIC is not verified in both lanes', () => {
  const text = 'POWER OF ATTORNEY\nPrincipal\nName: Ahmed Raza\nCNIC: 00000-0000000-0\nPlot: 34-C\nAttorney\nName: Zubair Khan\nCNIC: 00000-0000000-1\n';
  for (const ocr of [false, true]) {
    const x = Extraction.parseDocumentText(text, 'poa');
    assert.equal(Extraction.decide(x, REC, { ocr, records: DEMO_PROPERTIES }).status, 'not_verified', `ocr=${ocr}`);
  }
});

test('a document missing its CNIC or plot is unable_to_verify, not a fabricated match', () => {
  assert.equal(decideProp('PROPERTY RECORD\nOwner: Ahmed Raza\nPlot: 34-C\n', REC).status, 'unable_to_verify');
  assert.equal(decideProp('PROPERTY RECORD\nOwner: Ahmed Raza\nCNIC: 00000-0000000-0\n', REC).status, 'unable_to_verify');
});

test('optional descriptors absent from the document do not change a verified result; present-but-contradictory ones do', () => {
  assert.equal(decideProp(propDoc(REC.owner, REC.cnic, REC.plot), REC).status, 'verified');
  const withBadSurvey = propDoc(REC.owner, REC.cnic, REC.plot) + 'Survey No: SRV-OTHER-9\n';
  assert.equal(decideProp(withBadSurvey, REC).status, 'not_verified');
  const recNoSurvey = Object.assign({}, REC, { survey: '—' });
  assert.equal(decideProp(withBadSurvey, recNoSurvey).status, 'verified');   // nothing on record to contradict it
});

/* ---- 5. privacy: no record values in reasons, checks or comparison details ---------------------------- */

test('mismatch explanations never contain the values held on the record', () => {
  const cases = [
    propDoc('Zubair Khan', REC.cnic, REC.plot),
    propDoc(REC.owner, REC.cnic, '99-Z'),
    propDoc(REC.owner, '00000-0000000-9', REC.plot) + 'Plot: 34-C\n',
    propDoc(REC.owner, REC.cnic, REC.plot) + 'Survey No: SRV-OTHER-9\n' + 'Address: Somewhere Else Road\n',
  ];
  for (const text of cases) for (const ocr of [false, true]) {
    const x = Extraction.parseDocumentText(text, 'property');
    const d = Extraction.decide(x, REC, { ocr, records: DEMO_PROPERTIES });
    assert.deepEqual(leaks({ reasons: d.reasons, cmp: d.cmp }, REC, text), []);
  }
});

test('the full app result for a mismatching document leaks no record values (reasons, checks, limitations)', () => {
  const text = propDoc('Zubair Khan', REC.cnic, REC.plot);
  const r = buildAutomaticResult(Extraction.parseDocumentText(text, 'property'), { name: 't' }, 'pdf-text');
  assert.equal(r.status, 'not_verified');
  assert.deepEqual(leaks({ reasons: r.reasons, checks: r.checks, limitations: r.limitations }, REC, text), []);
  assert.ok(!JSON.stringify(r.reasons).includes(REC.owner));
});

test('an attorney mismatch reason does not reveal whom the CNIC is registered to', () => {
  const text = 'POWER OF ATTORNEY\nPrincipal\nName: Ahmed Raza\nCNIC: 00000-0000000-0\nPlot: 34-C\nAttorney\nName: Zubair Khan\nCNIC: 00000-0000000-1\n';
  const x = Extraction.parseDocumentText(text, 'poa');
  const d = Extraction.decide(x, REC, { ocr: false, records: DEMO_PROPERTIES });
  assert.doesNotMatch(JSON.stringify(d.reasons), /Bilal|Hassan/);
});

/* ---- 6. limitations text and stored history ------------------------------------------------------------ */

test('a verified result states what "verified" does not mean', () => {
  const x = Extraction.parseDocumentText(propDoc(REC.owner, REC.cnic, REC.plot), 'property');
  const r = buildAutomaticResult(x, { name: 't' }, 'pdf-text');
  assert.equal(r.status, 'verified');
  const text = r.limitations.join(' ');
  assert.match(text, /does not prove the document is genuine/i);
  assert.match(text, /legal validity/i);
});

test('a power-of-attorney result says legal validity, scope and current status were not checked', () => {
  const text = 'POWER OF ATTORNEY\nPrincipal\nName: Ahmed Raza\nCNIC: 00000-0000000-0\nPlot: 34-C\nAttorney\nName: Zubair Khan\nCNIC: 00000-0000000-7\n';
  const r = buildAutomaticResult(Extraction.parseDocumentText(text, 'poa'), { name: 't' }, 'pdf-text');
  assert.match(r.limitations.join(' '), /legal validity, scope, duration and current status of this power of attorney were not checked/);
});

test('sanitizeResultForStorage masks every CNIC, keeps the rest, and does not mutate the original', () => {
  const x = Extraction.parseDocumentText(propDoc(REC.owner, REC.cnic, REC.plot), 'property');
  const r = buildAutomaticResult(x, { name: 't' }, 'pdf-text');
  const before = JSON.stringify(r);
  const s = sanitizeResultForStorage(r);
  assert.equal(JSON.stringify(r), before);
  const stored = JSON.stringify(s);
  assert.ok(!stored.includes('0000000000000') && !stored.includes('00000-0000000-0'), 'full CNIC survived');
  assert.equal(s.status, r.status);
  assert.match(stored, /00000-\*{6}/);
});

/* ---- 7. result screen ---------------------------------------------------------------------------------- */

function renderResult(text, type, source = 'pdf-text') {
  resetDocState();
  docState.step = 'result';
  docState.result = buildAutomaticResult(Extraction.parseDocumentText(text, type), { name: 't' }, source);
  state.view = 'verify-document';
  render();
  return document.getElementById('app').innerHTML;
}

test('result screen: the matched record owner is never displayed, whatever the status', () => {
  for (const text of [propDoc(REC.owner, REC.cnic, REC.plot), propDoc('Zubair Khan', REC.cnic, REC.plot)]) {
    const html = renderResult(text, 'property');
    assert.ok(!/Owner on record/i.test(html));
    assert.ok(!html.includes(REC.owner) || text.includes(REC.owner));   // the document's own name may be shown as extracted
    if (!text.includes(REC.owner)) assert.ok(!html.includes(REC.owner), 'record owner shown for a document that does not carry it');
  }
});

test('result screen: a verified result lists its limitations, and an unverified one does not claim a link', () => {
  const html = renderResult(propDoc(REC.owner, REC.cnic, REC.plot), 'property');
  assert.match(html, /DOCUMENT VERIFIED/);
  assert.match(html, /does not prove the document is genuine/);
  assert.match(html, /not a confirmed link/);
});

test('result screen: conflicting CNIC values are masked on screen', () => {
  const html = renderResult(propDoc(REC.owner, '00000-0000000-0', REC.plot) + 'CNIC: 00000-0000000-5\n', 'property');
  assert.match(html, /conflicting values/);
  assert.ok(!html.includes('00000-0000000-5') && !html.includes('00000-0000000-0'), 'a full CNIC is on screen');
});
