/* data/documentTypes.js — Document-type definitions, required fields, status metadata, sample documents and demo records. */

/* ==================================================================
   VERIFY YOUR DOCUMENT
   A separate feature from "Verify This Property". Verify This Property
   checks an entire listed property across categories. Verify Your
   Document independently checks ONE document — even when the property
   is not listed in PROPERTIES at all. Analysis below is a deterministic
   demo engine (no OCR/forensics backend exists yet); it is written as
   small modular functions so a real service can replace runDocumentChecks()
   later without touching the UI layer.
   ================================================================== */
export const DOC_TYPES = ['Sale Deed','Lease Deed','Transfer Order','Allotment Letter','NOC','Power of Attorney','Ownership Document','Building Approval','Registry Document','Property Tax Document','Utility Document','Other / Unknown Document'];

export const DOC_FIELD_DEFS = {
  documentNumber:{label:'Document Number', ph:'e.g. SD-2026-0182'},
  date:{label:'Date', type:'date'},
  ownerName:{label:'Owner Name', ph:'e.g. Ahmed Ali'},
  sellerName:{label:'Seller Name', ph:''},
  buyerName:{label:'Buyer Name', ph:''},
  cnic:{label:'CNIC / Reference Number', ph:'e.g. 42101-1234567-1'},
  plotNumber:{label:'Plot Number', ph:'e.g. 34-C'},
  surveyNumber:{label:'Survey Number', ph:''},
  propertyAddress:{label:'Property Address', ph:''},
  area:{label:'Area / Scheme', ph:''},
  deh:{label:'Deh', ph:''},
  scheme:{label:'Scheme', ph:''},
  authority:{label:'Authority', ph:''},
  registrationNumber:{label:'Registration Number', ph:''},
  nocNumber:{label:'NOC Number', ph:''},
  notes:{label:'Additional Notes', type:'textarea'}
};

export const DOC_TYPE_FIELDS = {
  'Sale Deed':['documentNumber','date','ownerName','sellerName','buyerName','cnic','plotNumber','area','notes'],
  'Lease Deed':['documentNumber','date','ownerName','buyerName','plotNumber','area','notes'],
  'Transfer Order':['documentNumber','date','ownerName','plotNumber','surveyNumber','authority','notes'],
  'Allotment Letter':['documentNumber','date','ownerName','plotNumber','scheme','authority','notes'],
  'NOC':['nocNumber','date','ownerName','plotNumber','authority','notes'],
  'Power of Attorney':['documentNumber','date','ownerName','buyerName','cnic','notes'],
  'Ownership Document':['documentNumber','date','ownerName','plotNumber','area','notes'],
  'Building Approval':['documentNumber','date','ownerName','plotNumber','authority','notes'],
  'Registry Document':['registrationNumber','date','ownerName','plotNumber','surveyNumber','deh','notes'],
  'Property Tax Document':['registrationNumber','date','ownerName','propertyAddress','notes'],
  'Utility Document':['documentNumber','date','ownerName','propertyAddress','notes'],
  'Other / Unknown Document':['documentNumber','date','ownerName','plotNumber','propertyAddress','notes']
};

export const DOC_REQUIRED_FIELDS = {
  'Sale Deed':['ownerName','plotNumber'], 'Lease Deed':['ownerName','plotNumber'],
  'Transfer Order':['ownerName','plotNumber'], 'Allotment Letter':['ownerName','plotNumber'],
  'NOC':['ownerName','plotNumber'], 'Power of Attorney':['ownerName'],
  'Ownership Document':['ownerName','plotNumber'], 'Building Approval':['ownerName','plotNumber'],
  'Registry Document':['ownerName','plotNumber'], 'Property Tax Document':['ownerName','propertyAddress'],
  'Utility Document':['ownerName','propertyAddress'], 'Other / Unknown Document':['ownerName']
};

export const DOC_STATUS_META = {
  likely_original:{label:'Likely Original', icon:'✓', badge:'status-verified', tone:'ok',
    blurb:'The available checks did not identify major inconsistencies. This does not constitute official authentication.'},
  potentially_forged:{label:'Potentially Forged / Suspicious', icon:'⚠', badge:'status-issue', tone:'bad',
    blurb:'Possible inconsistencies or document anomalies were detected. Further review is recommended.'},
  review_required:{label:'Review Required', icon:'⚠', badge:'status-review', tone:'warn',
    blurb:'Some information could not be confirmed against available records.'},
  unable_to_determine:{label:'Unable to Determine', icon:'–', badge:'status-unchecked', tone:'mute',
    blurb:'The available information was insufficient to make an authenticity assessment.'}
};

export const AUTO_DOC_TYPES = [['cnic','CNIC'],['property','Property / House Document'],['sale_deed','Sale Deed'],['lease_deed','Lease Deed'],['allotment','Allotment Letter'],['transfer_order','Transfer Order'],['noc','NOC'],['poa','Power of Attorney'],['building_approval','Building Approval'],['property_tax','Property Tax'],['utility','Utility Bill'],['other','Other']];

export const AUTO_STATUS_META = {
  verified:{label:'DOCUMENT VERIFIED', icon:'✓', tone:'ok'},
  not_verified:{label:'DOCUMENT NOT VERIFIED', icon:'⚠', tone:'bad'},
  suspicious:{label:'POTENTIALLY FORGED / SUSPICIOUS', icon:'⚠', tone:'bad'},
  unable_to_verify:{label:'UNABLE TO VERIFY', icon:'–', tone:'mute'}
};

/* DEVELOPMENT / DEMO ONLY: "Try Sample Documents". Fetches the real sample
   file and sends it through the SAME docHandle-style pipeline as an
   upload (file -> OCR/PDF text -> extraction -> verification). It never
   sets a result directly. Requires the site to be served over http(s). */
export const SAMPLE_DOCS = [
  ['cnic','CNIC','cnic'],['property','Property Paper','property'],['sale_deed','Sale Deed','sale_deed'],['lease_deed','Lease Deed','lease_deed'],
  ['allotment','Allotment Letter','allotment'],['transfer_order','Transfer Order','transfer_order'],['noc','NOC','noc'],['poa','Power of Attorney','power_of_attorney'],
  ['building_approval','Building Approval','building_approval'],['property_tax','Property Tax','property_tax'],['utility','Utility Bill','utility']
];

/* Builds the same {status, checks, reasons, limitations, ...} result
   shape the UI expects, but from REAL extracted fields instead of
   typed-in ones. Distinguishes:
     - 'suspicious'      -> genuine internal conflict found in the document text
     - 'not_verified'    -> extracted values contradict an available record, or no record matches
     - 'unable_to_verify'-> not enough information was extracted to compare anything
     - 'verified'        -> everything that could be checked, checked out
   This function does NOT and cannot prove authenticity; it only
   compares what OCR read against the app's own demo records. */
/* Synthetic verification database (from property_database.json).
   Fictional records for testing only. */
export const DEMO_PROPERTIES = [
  {id:'DEMO-KPT-001', title:'Demo Property A', owner:'Ahmed Raza', cnic:'00000-0000000-0', plot:'34-C', survey:'SRV-TEST-001', area:'DHA Phase 6', size:'500 Sq. Yards', address:'House 12, Example Street, Demo Block, Karachi'},
  {id:'DEMO-KPT-002', title:'Demo Property B', owner:'Bilal Hassan', cnic:'00000-0000000-1', plot:'52-A', survey:'SRV-TEST-002', area:'Gulshan-e-Iqbal', size:'240 Sq. Yards', address:'House 25, Example Avenue, Demo Block, Karachi'},
  {id:'DEMO-KPT-003', title:'Demo Property C', owner:'Sara Ahmed', cnic:'00000-0000000-2', plot:'17-B', survey:'SRV-TEST-003', area:'Scheme 33', size:'400 Sq. Yards', address:'Plot 17-B, Example Road, Demo Block, Karachi'}
];
