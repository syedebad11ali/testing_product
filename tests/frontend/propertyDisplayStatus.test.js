import test from 'node:test';
import assert from 'node:assert/strict';
import { installDom } from './helpers/domStub.js';

installDom();
const { renderHome } = await import('../../frontend/js/features/home.js');
const { featuredCardHTML } = await import('../../frontend/js/features/featured.js');
const { renderDetail, renderReport, renderSubList } = await import('../../frontend/js/features/property.js');
const { PROPERTIES } = await import('../../frontend/js/data/properties.js');
const { overallStatus } = await import('../../frontend/js/domain/propertyStatus.js');
const { state } = await import('../../frontend/js/state/store.js');

test('browse, featured carousel, property detail, verification list and report show Verified', () => {
  const property = PROPERTIES.find((p) => p.id === 'p2');
  assert.equal(overallStatus(property), 'review', 'underlying verification checks remain unchanged');

  assert.match(renderHome(), /class="vrow[^"]*">✓ Verified<\/div>/);
  assert.match(featuredCardHTML(property), /class="fc-verif">&#10003; Verified<\/span>/);
  assert.match(renderDetail(property.id), /class="d-stat tone-ok">✓ Verified<\/div>/);
  assert.match(renderSubList('verifications'), /class="status-badge status-verified[^"]*">✓ Verified<\/span>/);
  assert.match(renderReport(property.id), /Overall Result[\s\S]*?<span class="status-badge status-verified/);
});

test('Report A Scam retains each property’s actual overall status', () => {
  const html = renderSubList('reports');
  assert.match(html, /Review Required/);
  assert.match(html, /Potential Issue/);
  assert.doesNotMatch(html, /status-badge status-verified[^"]*">✓ Verified/);
});

test('verification category results remain based on their original checks', async () => {
  const { renderVerify } = await import('../../frontend/js/features/property.js');
  const html = renderVerify('p2');
  assert.match(html, /Review Required/);
  assert.match(html, /Not Checked/);
});

test('Verify This Property follows Chat with seller in the same two-column action row', () => {
  const html = renderDetail('p1');
  const chat = html.indexOf('>Chat with seller</button>');
  const verify = html.indexOf('>🛡 Verify This Property</button>');
  assert.ok(chat >= 0 && verify > chat);
  assert.match(html.slice(html.indexOf('<div class="action-row">'), html.indexOf('</div>', html.indexOf('<div class="action-row">'))), /class="btn btn-primary"[^>]*>Chat with seller[\s\S]*class="verify-cta-btn"/);
});
