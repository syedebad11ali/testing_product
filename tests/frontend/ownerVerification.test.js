import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import OwnerVerification from '../../frontend/js/domain/ownerVerification.js';

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const files = OwnerVerification.CSV_FILES.map(name => ({ name, text: fs.readFileSync(path.join(root, 'public', name), 'utf8') }));
const store = OwnerVerification.createStore(OwnerVerification.parseFiles(files));

test('parses quoted commas and escaped quotes in CSV fields', () => {
  const rows = OwnerVerification.parseCsv('name,note\n"Example, Owner","says ""hello"""\n');
  assert.deepEqual(rows, [{ name: 'Example, Owner', note: 'says "hello"' }]);
});

test('rejects an unterminated quoted field instead of returning partial data', () => {
  assert.throws(() => OwnerVerification.parseCsv('a,b\n"oops,1\n'), /unterminated/i);
});

test('loads every property record from the five supplied CSV files', () => {
  assert.equal(store.recordCount, 16000);
  assert.equal(store.pricedCount, 13009);
  assert.deepEqual(Object.values(store.sourceCounts).reduce((sum, count) => sum + count, 0), 16000);
});

test('looks up a real CSV property and compounds its estimate', () => {
  const property = store.lookup('demo-kpt-8103');
  assert.equal(property.ownerName, 'Rahim Mahsud');
  assert.equal(property.propertyType, 'Apartment');
  assert.equal(property.price, 10000000);
  const result = store.forecast(property, 2);
  assert.equal(result.forecastPrice, Math.round(result.currentPrice * 1.05 ** 2 / 1000) * 1000);
  assert.ok(result.supportCount > 0);
});

test('uses an area fallback for an unpriced Commercial property', () => {
  const property = store.lookup('DEMO-KPT-15327');
  assert.equal(property.propertyType, 'Commercial');
  assert.equal(property.price, null);
  const estimate = store.estimate(property);
  assert.ok(estimate.price > 0);
  assert.match(estimate.label, /area mean/);
});

test('lookup of an unknown id returns nothing rather than throwing', () => {
  assert.ok(!store.lookup('NOPE-0000'));
});

test('loadStore surfaces a failed download as an Error the UI can show', async () => {
  const failing = async () => ({ ok: false, status: 404, text: async () => '' });
  await assert.rejects(() => OwnerVerification.loadStore(failing), Error);
});

test('the two copies of the dataset (frontend + backend) are byte-identical', () => {
  for (const name of ['apartments', 'commercials', 'houses', 'plots', 'portions']) {
    const a = fs.readFileSync(path.join(root, 'public', 'assets', 'Dataset', `${name}.csv`));
    const b = fs.readFileSync(path.join(root, 'backend', 'datasets', `${name}.csv`));
    assert.ok(a.equals(b), `${name}.csv differs between public/assets/Dataset and backend/datasets — run scripts/sync_datasets.py`);
  }
});
