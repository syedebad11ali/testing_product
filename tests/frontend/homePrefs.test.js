import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { restoreFilters, filtersPatch } from '../../frontend/js/features/homePrefs.js';
import { sanitize } from '../../frontend/js/core/prefs.js';

const AREAS = ['DHA Phase 6', 'Bahria Town', 'Gulshan-e-Iqbal'];
const TYPES = ['House', 'Apartment', 'Plot'];

test('restoreFilters maps saved codes back to the options the page offers (case-insensitive)', () => {
  assert.deepEqual(restoreFilters({ area: 'dha phase 6', ptype: 'house', sort: 'price_desc' }, AREAS, TYPES),
    { areaFilter: 'DHA Phase 6', typeFilter: 'House', sort: 'high' });
  assert.deepEqual(restoreFilters({ sort: 'price_asc' }, AREAS, TYPES), { sort: 'low' });
});

test('restoreFilters ignores unknown, tampered or malformed values and never returns them', () => {
  const evil = { area: '<img src=x onerror=1>', ptype: 'castle', sort: 'DROP TABLE', theme: 'dark' };
  assert.deepEqual(restoreFilters(evil, AREAS, TYPES), {});
  assert.deepEqual(restoreFilters({ area: 5, ptype: null, sort: ['newest'] }, AREAS, TYPES), {});
  assert.deepEqual(restoreFilters(null, AREAS, TYPES), {});
  assert.deepEqual(restoreFilters({ sort: 'relevance' }, AREAS, TYPES), {});   // valid cookie code the UI has no option for
});

test('filtersPatch produces values the shared sanitiser accepts, and clears with null', () => {
  const patch = filtersPatch({ areaFilter: 'DHA Phase 6', typeFilter: 'House', sort: 'low' });
  assert.deepEqual(sanitize(patch), { area: 'dha phase 6', ptype: 'house', sort: 'price_asc' });
  assert.deepEqual(sanitize(filtersPatch({ areaFilter: null, typeFilter: '', sort: 'large' })), {});   // "Largest" has no cookie code
  for (const area of AREAS) assert.ok('area' in sanitize(filtersPatch({ areaFilter: area, typeFilter: '', sort: 'newest' })), area);
});

test('home setters persist the choice and the free-text search is never stored', () => {
  const root = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
  const home = fs.readFileSync(path.join(root, 'frontend/js/features/home.js'), 'utf8');
  for (const fn of ['setArea', 'setTypeFilter', 'setSort']) assert.match(home, new RegExp(`function ${fn}\\([^)]*\\)\\{[^}]*saveHomeFilters`));
  assert.doesNotMatch(home.match(/function setSearch[^\n]*/)[0], /saveHomeFilters|writePrefs/);
});
