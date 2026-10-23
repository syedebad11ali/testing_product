/* features/ownerVerification.js — Owner Verification screen: loads the CSV store, looks up a property id, shows the price forecast. */
import { render } from '../app/router.js';
import { LOGO_URL } from '../config.js';
import { escapeHtml } from '../core/html.js';
import OwnerVerification from '../domain/ownerVerification.js';
import { ownerState, state } from '../state/store.js';

export function loadOwnerVerificationData(retry){
  if(retry){ ownerState.store=null; ownerState.error=null; ownerState.promise=null; }
  if(ownerState.store || ownerState.promise || ownerState.error) return;
  ownerState.promise = OwnerVerification.loadStore()
    .then(store=>{
      ownerState.store=store;
      ownerState.promise=null;
      if(state.view==='ownerverify') render();
    })
    .catch(error=>{
      ownerState.error=error && error.message ? error.message : 'Unable to load the property CSV files.';
      ownerState.promise=null;
      if(state.view==='ownerverify') render();
    });
}

function ownerPrice(value){ return 'PKR '+Math.round(value).toLocaleString('en-US'); }

function ownerDataField(label,value){
  return `<div class="owner-data-field"><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value==null || value===''?'Not recorded':String(value))}</dd></div>`;
}

export function renderOwnerForecast(record){
  const output=document.getElementById('ownerForecastOutput');
  if(!output) return;
  const raw=ownerState.forecastYears.trim();
  if(!raw){ output.innerHTML='<div class="owner-forecast-empty">Enter a whole number of years to view the scenario.</div>'; return; }
  const years=Number(raw);
  if(!Number.isInteger(years) || years<0 || years>50){
    output.innerHTML='<div class="owner-forecast-error">Enter a whole number from 0 to 50.</div>';
    return;
  }
  const result=ownerState.store.forecast(record,years,0.05);
  output.innerHTML=`
    <div class="owner-forecast-value">${ownerPrice(result.forecastPrice)}</div>
    ${result.range?`<div class="owner-forecast-range">Estimated range: ${ownerPrice(result.range.low)} – ${ownerPrice(result.range.high)}</div>`:''}
    <div class="owner-forecast-meta">Current estimate: ${ownerPrice(result.currentPrice)} · Assumes 5% annual appreciation · ${escapeHtml(result.method)} · ${result.supportCount.toLocaleString()} priced records · ${escapeHtml(result.confidence)} confidence</div>`;
}

export function lookupOwnerProperty(){
  if(!ownerState.store) return;
  const input=document.getElementById('ownerPropertyId');
  ownerState.id=(input ? input.value : ownerState.id).trim().toUpperCase();
  ownerState.result=ownerState.store.lookup(ownerState.id);
  ownerState.lookupError=ownerState.result ? '' : 'No property with that ID was found in the loaded CSV files.';
  ownerState.forecastYears='';
  render();
}

export function renderOwnerVerification(){
  const dataStatus=ownerState.error
    ? `<div class="owner-data-error">${escapeHtml(ownerState.error)} <button class="btn btn-outline" onclick="loadOwnerVerificationData(true)">Retry</button></div>`
    : ownerState.store
      ? `<div class="owner-data-loaded">Loaded ${ownerState.store.recordCount.toLocaleString()} property records, including ${ownerState.store.pricedCount.toLocaleString()} priced records, from the five CSV datasets.</div>`
      : '<div class="owner-data-loaded" role="status">Loading property records from the CSV files…</div>';
  const sourceList=ownerState.store
    ? `<div class="owner-source-list">${Object.entries(ownerState.store.sourceCounts).map(([name,count])=>`<span>${escapeHtml(name.replace(/\.csv$/i,''))} <strong>${count.toLocaleString()}</strong></span>`).join('')}</div>`
    : '';
  const record=ownerState.result;
  const recordPanel=record ? `
    <div class="owner-results">
      <section class="owner-panel">
        <div class="owner-panel-heading"><h2>Registered Property</h2><span>${escapeHtml(record.propertyId)}</span></div>
        <dl class="owner-data-grid">
          ${ownerDataField('Owner name',record.ownerName)}
          ${ownerDataField('Property owner',record.listedOwner)}
          ${ownerDataField('Previous owner',record.previousOwner)}
          ${ownerDataField('Property type',record.propertyType)}
          ${ownerDataField('Area',record.area)}
          ${ownerDataField('Block',record.block)}
          ${ownerDataField('House number',record.houseNumber)}
          ${ownerDataField('Street number',record.streetNumber)}
          ${ownerDataField('Rooms',record.rooms)}
          ${ownerDataField('Owner ID',record.ownerId)}
          ${ownerDataField('Listed price',record.price==null?'Not priced in dataset':ownerPrice(record.price))}
          ${ownerDataField('Source CSV',record.sourceFile)}
        </dl>
      </section>
      <section class="owner-panel">
        <div class="owner-panel-heading"><h2>Record Checks</h2></div>
        <dl class="owner-status-grid">
          ${ownerDataField('Ownership status',record.ownershipStatus)}
          ${ownerDataField('Legal check',record.legalCheck)}
          ${ownerDataField('Taxes status',record.taxesStatus)}
          ${ownerDataField('Utilities bill',record.utilitiesBill)}
        </dl>
        <p class="owner-disclaimer">These values are read from the supplied CSV record. They are not independently confirmed against an authority.</p>
      </section>
      <section class="owner-panel owner-forecast-panel">
        <div class="owner-panel-heading"><h2>Assumption-Based Price Forecast</h2><span>5% per year</span></div>
        <div class="owner-forecast-input">
          <label for="ownerForecastYears">Forecast horizon (years)</label>
          <input id="ownerForecastYears" type="number" min="0" max="50" step="1" inputmode="numeric" value="${escapeHtml(ownerState.forecastYears)}" oninput="setOwnerForecastYears(this.value)">
        </div>
        <div id="ownerForecastOutput" class="owner-forecast-output" aria-live="polite"><div class="owner-forecast-empty">Enter a whole number of years to view the scenario.</div></div>
        ${record.price==null?'<p class="owner-disclaimer">This property has no recorded sale price. Its estimate uses priced properties in the same area/type where available, then falls back to area or global averages.</p>':''}
        <p class="owner-disclaimer">This compounds a current dataset estimate; the CSVs have no dated price history, so the future value is an assumption-based scenario, not a time-series prediction.</p>
      </section>
    </div>` : (ownerState.lookupError ? `<div class="owner-lookup-error" role="alert">${escapeHtml(ownerState.lookupError)}</div>` : '');

  return `
  <div class="header" style="padding-bottom:20px;">
    <div class="header-top">
      <button class="icon-btn" onclick="nav('home')" aria-label="Back to home"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m15 18-6-6 6-6"/></svg></button>
      <div class="logo-badge"><img src="${LOGO_URL}" alt="Karachi Property Trust"></div>
    </div>
    <div class="brand-block"><div class="brand" style="font-size:19px;">Owner Verification System</div><div class="tagline">Look up property ownership and record checks from the supplied datasets</div></div>
  </div>
  <main class="owner-verification">
    <section class="owner-lookup-panel">
      <div class="owner-lookup-heading"><div><h2>Find a Property Record</h2><p>Search by the Property ID printed in the CSV datasets.</p></div></div>
      <form class="owner-lookup-form" onsubmit="event.preventDefault();lookupOwnerProperty();">
        <div><label for="ownerPropertyId">Property ID</label><input id="ownerPropertyId" type="text" value="${escapeHtml(ownerState.id)}" placeholder="e.g. DEMO-KPT-8103" autocomplete="off" spellcheck="false" oninput="setOwnerPropertyId(this.value)"></div>
        <button class="btn btn-primary" type="submit" ${ownerState.store?'':'disabled'}>Search records</button>
      </form>
      <div class="owner-dataset-summary">${dataStatus}${sourceList}</div>
    </section>
    ${recordPanel}
    <p class="owner-disclaimer owner-page-disclaimer">Owner, legal, tax, utility, and price fields are displayed as provided in the CSVs. This tool is a dataset lookup, not official identity or title verification.</p>
  </main>`;
}

/* Input handlers (replace former inline global assignments). */
export function setOwnerPropertyId(value){ ownerState.id = value; }
export function setOwnerForecastYears(value){ ownerState.forecastYears = value; renderOwnerForecast(ownerState.result); }
