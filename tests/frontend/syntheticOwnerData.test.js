import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import crypto from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { PROPERTIES } from '../../frontend/js/data/properties.js';
import { DEMO_PROPERTIES, DOC_FIELD_DEFS, SAMPLE_DOCS } from '../../frontend/js/data/documentTypes.js';

/* G6.2a-3 (Part A): the public frontend, the served sample datasets, the tests and the fixtures contain only SYNTHETIC identity data.
 * - every CNIC-shaped value (formatted NNNNN-NNNNNNN-N, masked NNNNN-******N-N, or a bare 13-digit run on a line - or under a CSV header - that talks about a CNIC)
 *   must start with the synthetic area code 00000; test files may also use the explicit mismatch prefixes below (to add one, edit this file);
 * - the eight demo records p1-p8 carry distinct "Demo ..." owners and distinct 00000- CNICs (p5 / p7, the companies, have none);
 * - failures print only file:line and a masked value, never a complete identifier. */
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const SYNTHETIC = '00000';
const TEST_ONLY_MISMATCH_PREFIXES = ['90000', '90008', '99000'];   // deliberate "wrong person" values used by fixtures
const TEXT_EXT = new Set(['.js', '.mjs', '.html', '.css', '.json', '.txt', '.md', '.csv', '.svg', '.xml']);
const SERVED_ROOTS = ['frontend', 'public'];
const TEST_ROOTS = ['tests/frontend', 'tests/fixtures'];

const FORMATTED = /(?<!\d)\d{5}-[\d*]{7}-\d(?!\d)/g;          // includes masked forms such as 00000-******1-0
const BARE13 = /(?<!\d)\d{13}(?!\d)/g;
const mentionsCnic = (line) => /cnic/i.test(line);

const mask = (v) => `${v.slice(0, 5)}-*******-${v.slice(-1)}`;   // what a failure message may show

/** CNIC-shaped values in one text. Bare 13-digit runs count only on a line that mentions a CNIC, or in a CSV whose header does
 *  (timestamps and other numbers are not identifiers). */
export function findIdentifiers(text, { csv = false } = {}) {
  const found = [], lines = text.split('\n'), headerSaysCnic = csv && mentionsCnic(lines[0] || '');
  lines.forEach((line, i) => {
    for (const m of line.matchAll(FORMATTED)) found.push({ line: i + 1, value: m[0], kind: m[0].includes('*') ? 'masked' : 'formatted' });
    if (headerSaysCnic || mentionsCnic(line)) for (const m of line.matchAll(BARE13)) found.push({ line: i + 1, value: m[0], kind: 'bare' });
  });
  return found;
}
const prefixOf = (value) => value.replace(/\D/g, '').slice(0, 5);
const allowed = (value, inTests) => prefixOf(value) === SYNTHETIC || (inTests && TEST_ONLY_MISMATCH_PREFIXES.includes(prefixOf(value)));

function* walk(dir) {
  if (!fs.existsSync(dir)) return;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === 'node_modules' || entry.name.startsWith('.git')) continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) yield* walk(full);
    else if (TEXT_EXT.has(path.extname(entry.name).toLowerCase())) yield full;
  }
}
/** Violations (file:line + masked value) under the given roots. */
export function scanTree(base, roots, inTests) {
  const bad = []; let files = 0, values = 0;
  for (const r of roots) for (const file of walk(path.join(base, r))) {
    let text; try { text = fs.readFileSync(file, 'utf8'); } catch { continue; }
    files += 1;
    for (const f of findIdentifiers(text, { csv: path.extname(file).toLowerCase() === '.csv' })) { values += 1; if (!allowed(f.value, inTests)) bad.push(`${path.relative(base, file)}:${f.line} ${f.kind} ${mask(f.value)}`); }
  }
  return { bad, files, values };
}

/* ---- the scanner itself must work (non-vacuous) ---- */
const OLD_FORMATTED = ['42101', '1234567', '1'].join('-');      // assembled so this file does not contain one
const OLD_MASKED = ['42101', '******7', '1'].join('-');
const OLD_BARE = ['42101', '1234567', '1'].join('');

test('self-test: an old-style CNIC is detected in every form (and the message never shows it whole)', () => {
  const hits = findIdentifiers(`a\nName: x CNIC: ${OLD_FORMATTED}\nmasked ${OLD_MASKED}\nbare cnic ${OLD_BARE}`);
  assert.deepEqual(hits.map((h) => [h.line, h.kind]), [[2, 'formatted'], [3, 'masked'], [4, 'bare']]);
  assert.ok(hits.every((h) => !allowed(h.value, true)), 'old-style values are not allowed even in tests');
  assert.ok(hits.every((h) => !mask(h.value).includes('1234567')), 'the printed form hides the serial');
});
test('self-test: synthetic and allow-listed values pass, timestamps and other numbers are not an identifier', () => {
  assert.ok(findIdentifiers('CNIC 00000-0000101-0, masked 00000-******1-0').every((h) => allowed(h.value, false)));
  assert.ok(findIdentifiers('mismatch 90000-0000000-0').every((h) => allowed(h.value, true) && !allowed(h.value, false)));
  assert.deepEqual(findIdentifiers('Created at 1700000000000 ms, not an identifier'), []);
  assert.deepEqual(findIdentifiers('order 1234567890123 shipped'), []);
  assert.deepEqual(findIdentifiers('id,price\n1,1234567890123\n', { csv: true }), [], 'a CSV without an identity column is not an identifier file');
  assert.equal(findIdentifiers(`id,cnic\n1,${OLD_BARE}\n`, { csv: true }).length, 1, 'a CSV with a CNIC column is');
});
test('self-test: the tree walker flags a planted old-style value in a temp project and reads nothing it should skip', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'kpt-scan-'));
  try {
    fs.mkdirSync(path.join(tmp, 'frontend', 'js'), { recursive: true }); fs.mkdirSync(path.join(tmp, 'public'), { recursive: true });
    fs.writeFileSync(path.join(tmp, 'frontend', 'js', 'ok.js'), "const a = '00000-0000101-0';\n");
    fs.writeFileSync(path.join(tmp, 'frontend', 'js', 'bad.js'), `const a = 'x';\nconst b = '${OLD_FORMATTED}';\n`);
    fs.writeFileSync(path.join(tmp, 'public', 'data.csv'), `id,cnic\n1,${OLD_BARE}\n`);
    fs.writeFileSync(path.join(tmp, 'public', 'image.png'), Buffer.from(OLD_FORMATTED));   // binary type: not scanned
    const r = scanTree(tmp, SERVED_ROOTS, false);
    assert.deepEqual(r.bad.map((b) => b.split(' ')[0]).sort(), [path.join('frontend', 'js', 'bad.js') + ':2', path.join('public', 'data.csv') + ':2'].sort());
    assert.equal(r.files, 3);
    assert.ok(r.bad.every((b) => !b.includes('1234567')), 'failure text never carries the full value');
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
});

/* ---- the real project ---- */
test('served files (frontend/, public/ incl. the sample datasets) contain only synthetic CNIC-shaped values', () => {
  const r = scanTree(ROOT, SERVED_ROOTS, false);
  assert.ok(r.files > 50, `scanned ${r.files} files`);
  assert.ok(fs.existsSync(path.join(ROOT, 'public', 'assets', 'Dataset')), 'the public sample datasets are part of the scan');
  assert.deepEqual(r.bad, [], 'non-synthetic CNIC-shaped values in served files');
});
test('tests and fixtures contain only synthetic values or the documented mismatch prefixes', () => {
  const r = scanTree(ROOT, TEST_ROOTS, true);
  assert.ok(r.files > 20 && r.values > 20, `scanned ${r.files} files, ${r.values} values`);
  assert.deepEqual(r.bad, [], 'non-synthetic CNIC-shaped values in tests/fixtures');
});

test('p1-p8: eight records, distinct "Demo" owners, distinct 00000- CNICs, companies without a CNIC', () => {
  assert.deepEqual(PROPERTIES.map((p) => p.id), ['p1', 'p2', 'p3', 'p4', 'p5', 'p6', 'p7', 'p8']);
  for (const p of PROPERTIES) assert.match(p.owner, /^Demo (Person|Company) [A-Z][a-z]+$/, p.id);
  assert.equal(new Set(PROPERTIES.map((p) => p.owner)).size, 8, 'owners are distinct');
  const withCnic = PROPERTIES.filter((p) => p.cnic);
  for (const p of withCnic) assert.match(p.cnic, /^00000-\d{7}-\d$/, p.id);
  assert.equal(new Set(withCnic.map((p) => p.cnic)).size, withCnic.length, 'CNICs are distinct');
  assert.deepEqual(PROPERTIES.filter((p) => !p.cnic).map((p) => p.id), ['p5', 'p7'], 'only the two companies have no CNIC');
  assert.deepEqual(PROPERTIES.filter((p) => /Company/.test(p.owner)).map((p) => p.id), ['p5', 'p7']);
  for (const id of ['p5', 'p7']) assert.equal(PROPERTIES.find((p) => p.id === id).cnic, undefined, `${id} stays without a CNIC`);
});
test('p1-p8 values do not collide with DEMO_PROPERTIES or the fixture records', () => {
  const fixture = JSON.parse(fs.readFileSync(path.join(ROOT, 'tests', 'fixtures', 'property_database.json'), 'utf8'));
  const text = JSON.stringify(fixture);
  const taken = new Set([...DEMO_PROPERTIES.map((p) => p.cnic), ...(text.match(FORMATTED) || [])]);
  const takenNames = new Set(DEMO_PROPERTIES.map((p) => p.owner));
  for (const p of PROPERTIES) { assert.ok(!p.cnic || !taken.has(p.cnic), `${p.id} CNIC collides`); assert.ok(!takenNames.has(p.owner), `${p.id} owner collides`); }
});
/* SHA-256 of the eight REMOVED owner names (lower case): lets the test notice one coming back without printing or storing the names. */
const REMOVED_OWNER_HASHES = new Set(["21db79088097ca2ec055cd00902114ccfdfd2e3939d3a21c7ffb71e42b35c50b", "15603b38f003860473f66566e4bad3ea96481423c034e0bf89ed8f0947e2550d", "f72426ce4993e4cf40adb4715b53294144490bd13d71f167de1be7d3ebf5e57b", "00d4e9e016bb420d5fd5bea255dfe2a9d87ccb914441c70934e3a505e846f14d", "6a8ab5a2dc9cf229c47449ad3ca6effd799e0bdaea849b9b1a67cc5a8ab7f579", "ef62fc1857eaf62421f9845d748b03b14ca54b96c84fbc5facb1d9431c01140c", "dedb8fb68d0df07657dbe87723815e2a520f8af5906d262863ab001dee72e82f", "31e7dd89509e40010f3e28e4e3e5a43e5fc350825e4df92a14cff6750c81b42a"]);
test('none of the eight removed owner names (checked by hash) is present in served or test text', () => {
  const sha = (x) => crypto.createHash('sha256').update(x).digest('hex');
  assert.equal(REMOVED_OWNER_HASHES.size, 8);
  const hits = [];
  for (const root of [...SERVED_ROOTS, ...TEST_ROOTS]) for (const file of walk(path.join(ROOT, root))) {
    let text; try { text = fs.readFileSync(file, 'utf8'); } catch { continue; }
    text.split('\n').forEach((line, i) => { for (const m of line.matchAll(/\b([A-Za-z]+) (?=([A-Za-z]+)\b)/g)) if (REMOVED_OWNER_HASHES.has(sha(`${m[1]} ${m[2]}`.toLowerCase()))) hits.push(`${path.relative(ROOT, file)}:${i + 1}`); });
  }
  assert.deepEqual(hits, [], 'a removed owner name is back');
  const probe = ['demo', 'person'].join(' ');   // the detector really hashes word pairs: a pair that is NOT removed is simply not a hit
  assert.equal(REMOVED_OWNER_HASHES.has(sha(probe)), false);
});

test('exported document placeholders and sample documents contain no real-shaped identifiers', () => {
  const strings = [];
  const collect = (v) => { if (typeof v === 'string') strings.push(v); else if (Array.isArray(v)) v.forEach(collect); else if (v && typeof v === 'object') Object.values(v).forEach(collect); };
  collect(Object.values(DOC_FIELD_DEFS).map((d) => d.ph)); collect(SAMPLE_DOCS); collect(DEMO_PROPERTIES);
  assert.ok(strings.length > 10, 'placeholders and samples were really collected');
  assert.equal(DOC_FIELD_DEFS.cnic.ph, 'e.g. 00000-0000000-0');
  assert.doesNotMatch(DOC_FIELD_DEFS.ownerName.ph, /\d/, 'the owner-name placeholder names nobody');
  for (const s of strings) for (const f of findIdentifiers(`CNIC ${s}`)) assert.ok(allowed(f.value, false), `exported value ${mask(f.value)}`);
  const property = fs.readFileSync(path.join(ROOT, 'frontend', 'js', 'features', 'property.js'), 'utf8');
  const placeholders = [...property.matchAll(/placeholder="([^"]*)"/g)].map((m) => m[1]);
  assert.ok(placeholders.some((p) => p === 'e.g. 00000-0000000-0'), 'the CNIC input placeholder is the demo format');
  for (const p of placeholders) for (const f of findIdentifiers(p)) assert.ok(allowed(f.value, false), `property.js placeholder ${mask(f.value)}`);
});
