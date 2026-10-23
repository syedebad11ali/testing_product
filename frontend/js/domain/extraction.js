/* ==================================================================
   DOCUMENT EXTRACTION ENGINE (v2)
   Pure functions only — no DOM, no fetch — so this can be unit tested
   in plain Node against real OCR/pdftotext output, separately from the
   OCR engine itself. See tests/frontend/extraction.test.js (synthetic layouts)
   and scripts/manifest-report.mjs (the real dataset: tests/fixtures/ +
   manifest.json).

   v2 adds ROLE AWARENESS. Evidence from the real dataset showed several
   document types repeat the same label ("NAME", "CNIC") for two
   different people (Seller vs Buyer, Transferor vs Transferee,
   Principal vs Attorney), which a single-field-per-label design misreads
   as an internal conflict on a perfectly valid document. v2 tracks the
   nearest preceding section header ("SELLER" / "BUYER" / etc.) and tags
   each captured value with a role, so multi-party fields stay separate
   instead of collapsing into a false conflict.
   ================================================================== */

  var MAX_VALUE_LEN = 90;

  // Words that show up in signature-block footers ("OWNER AUTHORITY REP
  // WITNESS") right after a role word with no real separator. Without this
  // guard, a bare role label at the end of a document swallows the next
  // footer words as if they were its value. Built directly from real
  // OCR/PDF-text footers observed in the sample set.
  var ROLE_STOPWORDS = ['authority','rep','witness','officer','registrar','holder','issuing','card',
    'billing','transferor','transferee','seller','buyer','principal','attorney','lessor','lessee',
    'allottee','applicant','customer','owner','payer','tax','approving'];

  function isStopwordOnly(value){
    var words = value.toLowerCase().replace(/[^a-z\s]/g,'').trim().split(/\s+/).filter(Boolean);
    if(!words.length) return false;
    return words.every(function(w){ return ROLE_STOPWORDS.indexOf(w) !== -1; });
  }

  // ---- token scanning -------------------------------------------------
  // One pass over the text. Section headers (SELLER/BUYER/TRANSFEROR/...)
  // update `currentSection`; every following bare NAME/CNIC label is
  // tagged with that role until the next section header appears.
  var SECTION_HEADERS = {seller:'seller', buyer:'buyer', transferor:'transferor', transferee:'transferee', principal:'principal', attorney:'attorney'};

  var TOKEN_RE = /\b(?<sec>seller|buyer|transferor|transferee|principal|attorney)\b|\b(?<allottee>allottee\s*name)\b|\b(?<customer>customer\s*name)\b|\b(?<father>father\s*\/?\s*husband\s*name|father\s*name|husband\s*name)\b|\b(?<owner>owner)\b|\b(?<applicant>applicant)\b|\b(?<lessor>lessor)\b|\b(?<lessee>lessee)\b|\b(?<name>name)\b|\b(?<cnic>cnic\s*(?:no\.?|number|#|\/\s*reference)?|nic\s*(?:no\.?|number|#)?)\b|\b(?<plot>plot\s*(?:no\.?|number|#)?)\b|\b(?<survey>survey\s*(?:no\.?|number|#)?)\b|\b(?<address>(?:property\s*)?address)\b|\b(?<approvedarea>approved\s*area)\b|\b(?<size>property\s*size|plot\s*size)\b|\b(?<paymentstatus>payment\s*status)\b/gi;

  var CNIC_ROLE_SUFFIX_RE = /^\s*\(\s*(lessor|lessee|seller|buyer|principal|attorney|transferor|transferee)\s*\)/i;

  function scanTokens(text){
    var re = new RegExp(TOKEN_RE.source, 'gi');
    var tokens = [];
    var currentSection = null;
    var m;
    while((m = re.exec(text))){
      var g = m.groups, end = m.index + m[0].length, kind = null, role = null;
      if(g.sec !== undefined){ currentSection = SECTION_HEADERS[g.sec.toLowerCase()] || null; continue; }
      if(g.allottee !== undefined){ kind='name'; role='allottee'; }
      else if(g.customer !== undefined){ kind='name'; role='customer'; }
      else if(g.father !== undefined){ kind='name'; role='father'; }
      else if(g.owner !== undefined){ kind='name'; role='owner'; }
      else if(g.applicant !== undefined){ kind='name'; role='applicant'; }
      else if(g.lessor !== undefined){ kind='name'; role='lessor'; }
      else if(g.lessee !== undefined){ kind='name'; role='lessee'; }
      else if(g.name !== undefined){ kind='name'; role = currentSection || 'primary'; }
      else if(g.cnic !== undefined){
        kind='cnic'; role = currentSection || 'primary';
        var suffixMatch = text.slice(end, end+20).match(CNIC_ROLE_SUFFIX_RE);
        if(suffixMatch){ role = suffixMatch[1].toLowerCase(); end += suffixMatch[0].length; re.lastIndex = end; }
      }
      else if(g.plot !== undefined){ kind='plot'; role='primary'; }
      else if(g.survey !== undefined){ kind='survey'; role='primary'; }
      else if(g.address !== undefined){ kind='address'; role='primary'; }
      else if(g.approvedarea !== undefined){ kind='approvedArea'; role='primary'; }
      else if(g.size !== undefined){ kind='approvedArea'; role='primary'; }
      else if(g.paymentstatus !== undefined){ kind='paymentStatus'; role='primary'; }
      if(kind) tokens.push({kind:kind, role:role, start:m.index, end:end});
      if(m.index === re.lastIndex) re.lastIndex++;
    }
    return tokens;
  }

  function captureValue(text, endIdx, boundaryIdx){
    var slice = text.slice(endIdx, Math.min(boundaryIdx, text.length, endIdx + MAX_VALUE_LEN + 40));
    slice = slice.replace(/^[\s:#.\-,]+/, '');
    var nl = slice.indexOf('\n');
    if(nl !== -1) slice = slice.slice(0, nl);
    slice = slice.replace(/[\s,;:.\-]+$/, '');
    return slice.slice(0, MAX_VALUE_LEN).trim();
  }

  function rawOccurrencesByKind(text, kind){
    var tokens = scanTokens(text || '');
    var out = [];
    for(var i = 0; i < tokens.length; i++){
      if(tokens[i].kind !== kind) continue;
      var boundary = (i + 1 < tokens.length) ? tokens[i + 1].start : text.length;
      var value = captureValue(text, tokens[i].end, boundary);
      out.push({raw:value, role:tokens[i].role, index:tokens[i].start});
    }
    return out;
  }

  // ---- per-value normalization / validation ------------------------------

  function normalizeCnicCandidate(raw){
    if(!raw) return null;
    var cleaned = raw.replace(/[Oo]/g,'0').replace(/[IiLl]/g,'1').replace(/[^\d\-]/g,'');
    var digits = cleaned.replace(/-/g,'');
    if(!/^\d{13}$/.test(digits)) return null;
    return {digits:digits, display:digits.slice(0,5)+'-'+digits.slice(5,12)+'-'+digits.slice(12)};
  }

  function normalizePlotCandidate(raw){
    if(!raw) return null;
    var v = raw.trim();
    if(!v || v.length > 20) return null;
    if(!/[0-9]/.test(v)) return null;
    if(/^(cnic|nic|name|owner)/i.test(v)) return null;
    if(isStopwordOnly(v)) return null;
    var display = v.replace(/\s+/g,'').toUpperCase();
    return {display:display, key:display};
  }

  function normalizeNameCandidate(raw){
    if(!raw) return null;
    var v = raw.trim().replace(/\s+/g,' ');
    if(!v || v.length > 60) return null;
    if(/^(cnic|nic|plot)/i.test(v)) return null;
    if(isStopwordOnly(v)) return null;
    var letters = (v.match(/[a-zA-Z]/g) || []).length;
    if(letters < 2) return null;
    var digits = (v.match(/[0-9]/g) || []).length;
    if(digits > letters) return null;
    return {display:v, key:v.toLowerCase().replace(/[^a-z0-9]/g,'')};
  }

  function normalizeGenericCandidate(raw){
    if(!raw) return null;
    var v = raw.trim().replace(/\s+/g,' ');
    if(!v) return null;
    if(isStopwordOnly(v)) return null;
    return {display:v, key:v.toLowerCase().replace(/[^a-z0-9]/g,'')};
  }

  var NORMALIZERS = {cnic:normalizeCnicCandidate, plot:normalizePlotCandidate, name:normalizeNameCandidate,
    survey:normalizeGenericCandidate, address:normalizeGenericCandidate, approvedArea:normalizeGenericCandidate,
    paymentStatus:normalizeGenericCandidate};

  function keyOf(kind, c){ return kind === 'cnic' ? c.digits : c.key; }
  function displayOf(c){ return c.display; }

  // Builds {found, value, display, conflict, values, occurrenceCount} for
  // ONE role bucket of one field kind (e.g. kind='name', role='seller').
  function buildFieldResult(kind, occurrencesForRole){
    var normalizer = NORMALIZERS[kind];
    var candidates = [];
    occurrencesForRole.forEach(function(o){ var c = normalizer(o.raw); if(c) candidates.push(c); });
    if(!candidates.length) return {found:false, value:null, display:null, conflict:false, values:[], occurrenceCount:occurrencesForRole.length};
    var byKey = {}, order = [];
    candidates.forEach(function(c){ var k = keyOf(kind,c); if(!(k in byKey)){ byKey[k]=c; order.push(k); } });
    if(order.length === 1){
      var only = byKey[order[0]];
      return {found:true, value:keyOf(kind,only), display:displayOf(only), conflict:false, values:[displayOf(only)], occurrenceCount:candidates.length};
    }
    return {found:true, value:null, display:null, conflict:true, values:order.map(function(k){ return displayOf(byKey[k]); }), occurrenceCount:candidates.length};
  }

  // Splits occurrences of a kind by role, returning {role: fieldResult}.
  function extractByRole(text, kind){
    var occ = rawOccurrencesByKind(text, kind);
    var byRole = {};
    occ.forEach(function(o){ (byRole[o.role] = byRole[o.role] || []).push(o); });
    var out = {};
    Object.keys(byRole).forEach(function(role){ out[role] = buildFieldResult(kind, byRole[role]); });
    return out;
  }

  var EMPTY_FIELD = {found:false, value:null, display:null, conflict:false, values:[], occurrenceCount:0};

  // Back-compat single-field helpers (role-agnostic — used by the plain
  // synthetic-layout tests, where there is only ever one role: 'primary').
  function pickPrimaryOrOnly(byRole, preferredRoles){
    for(var i=0;i<preferredRoles.length;i++){ if(byRole[preferredRoles[i]]) return byRole[preferredRoles[i]]; }
    var roles = Object.keys(byRole);
    if(roles.length === 1) return byRole[roles[0]];
    if(roles.length === 0) return EMPTY_FIELD;
    var allValues = [];
    roles.forEach(function(r){ if(byRole[r].found) allValues = allValues.concat(byRole[r].values); });
    return {found:allValues.length>0, value:null, display:null, conflict:false, values:allValues, occurrenceCount:allValues.length, multiRole:true};
  }
  function extractOwnerName(text){ return pickPrimaryOrOnly(extractByRole(text,'name'), ['primary','owner']); }
  function extractPlotNumber(text){ return buildFieldResult('plot', rawOccurrencesByKind(text,'plot')); }
  function extractCNIC(text){ return pickPrimaryOrOnly(extractByRole(text,'cnic'), ['primary']); }

  // ---- document type detection -------------------------------------------

  var DOC_TYPE_RULES = [
    {type:'Sale Deed', re:/\bsale\s*deed\b/i},
    {type:'Lease Deed', re:/\blease\s*deed\b/i},
    {type:'Allotment Letter', re:/\ballotment\s*(letter)?\b/i},
    {type:'Transfer Order', re:/\btransfer\s*order\b/i},
    {type:'Power of Attorney', re:/\bpower\s*of\s*attorney\b/i},
    {type:'NOC', re:/\bno\s*objection\s*certificate\b|\bnoc\b/i},
    {type:'Building Approval', re:/\bbuilding\s*approval\b|\bapproved\s*plan\b/i},
    {type:'Property Tax Document', re:/\bproperty\s*tax\b/i},
    {type:'Utility Bill', re:/\butility\b|\bk-?electric\b|\bkwsb\b|\bsui\s*gas\b|electric\s*service/i},
    {type:'CNIC', re:/\bidentity\s*card\b/i},
    {type:'Property Ownership Paper', re:/\bproperty\s*record\b|\bownership\s*paper\b/i},
    {type:'Registry Document', re:/\bregistry\b|\bregistration\s*(no|number)\b/i}
  ];

  function detectDocumentType(text){
    if(!text || !text.trim()) return {type:'Unable to Determine', confidence:'none'};
    for(var i=0;i<DOC_TYPE_RULES.length;i++){ if(DOC_TYPE_RULES[i].re.test(text)) return {type:DOC_TYPE_RULES[i].type, confidence:'keyword'}; }
    return {type:'Unable to Determine', confidence:'none'};
  }

  // ---- document-type verification profiles ---------------------------------
  // nameRole/cnicRole: which role bucket represents "the person to compare
  // against the property's owner/CNIC on file" for this document type.
  // fields: which extracted fields are meaningful checks for this type.
  var TYPE_PROFILES = {
    cnic:              {label:'CNIC',                      nameRole:'primary',    cnicRole:'primary',    fields:['name','cnic']},
    property:          {label:'Property / House Document',  nameRole:'owner',      cnicRole:'primary',    fields:['name','cnic','plot']},
    sale_deed:         {label:'Sale Deed',                  nameRole:'seller',     cnicRole:'seller',     fields:['name','cnic','plot']},
    lease_deed:        {label:'Lease Deed',                 nameRole:'lessor',     cnicRole:'lessor',     fields:['name','cnic','plot','survey']},
    allotment:         {label:'Allotment Letter',           nameRole:'allottee',   cnicRole:'primary',    fields:['name','cnic','plot']},
    transfer_order:    {label:'Transfer Order',             nameRole:'transferor', cnicRole:'transferor', fields:['name','cnic','plot']},
    noc:               {label:'NOC',                        nameRole:'applicant',  cnicRole:'primary',    fields:['name','cnic','plot']},
    poa:               {label:'Power of Attorney',          nameRole:'principal',  cnicRole:'principal',  fields:['name','cnic','plot']},
    building_approval: {label:'Building Approval',          nameRole:'owner',      cnicRole:'primary',    fields:['name','cnic','plot','approvedArea']},
    property_tax:      {label:'Property Tax Document',      nameRole:'owner',      cnicRole:'primary',    fields:['name','cnic','plot','paymentStatus']},
    utility:           {label:'Utility Bill',               nameRole:'customer',   cnicRole:'primary',    fields:['name','address']},
    other:             {label:'Other / Unknown Document',   nameRole:'primary',    cnicRole:'primary',    fields:['name','cnic','plot']}
  };

  var SUSPICIOUS_STATUS_WORDS = /overdue|does not match|discrepancy|mismatch|conflict|disputed|default/i;

  // ---- full-text parse ------------------------------------------------------
  function parseDocumentText(text, typeKey){
    var profile = TYPE_PROFILES[typeKey] || TYPE_PROFILES.other;
    var byNameRole = extractByRole(text, 'name');
    var byCnicRole = extractByRole(text, 'cnic');

    return {
      documentType: detectDocumentType(text),
      profile: profile,
      ownerName: byNameRole[profile.nameRole] || EMPTY_FIELD,
      cnic: byCnicRole[profile.cnicRole] || EMPTY_FIELD,
      plotNumber: buildFieldResult('plot', rawOccurrencesByKind(text,'plot')),
      surveyNumber: buildFieldResult('survey', rawOccurrencesByKind(text,'survey')),
      address: buildFieldResult('address', rawOccurrencesByKind(text,'address')),
      approvedArea: buildFieldResult('approvedArea', rawOccurrencesByKind(text,'approvedArea')),
      paymentStatus: buildFieldResult('paymentStatus', rawOccurrencesByKind(text,'paymentStatus')),
      allRoles: {name:byNameRole, cnic:byCnicRole},
      rawTextLength:(text||'').length
    };
  }

  // ---- property matching / comparison ---------------------------------------


  // Characters Tesseract commonly confuses. Used ONLY to tell "clearly
  // different value" apart from "differs only by a likely OCR misread"
  // (which must not be reported as a proven mismatch).
  var CONFUSION = {'0':'0','O':'0','o':'0','9':'0','D':'0','Q':'0','8':'8','B':'8','1':'1','I':'1','l':'1','|':'1','C':'C','\u20ac':'C','G':'C','5':'5','S':'5','2':'2','Z':'2'};
  function confusionKey(s){ return (s||'').toString().replace(/[^A-Za-z0-9\u20ac|]/g,'').split('').map(function(ch){ return CONFUSION[ch]||ch.toUpperCase(); }).join(''); }
  function ocrConfusable(a,b){ return a!==b && confusionKey(a)===confusionKey(b); }

  function docNormalizeKey(s){ return (s||'').toString().toLowerCase().replace(/[^a-z0-9]/g,''); }
  function fuzzyContains(hay, needle){ hay=docNormalizeKey(hay); needle=docNormalizeKey(needle); return !!needle && hay.indexOf(needle)!==-1; }

  function matchProperty(extracted, properties){
    var plotKey = extracted.plotNumber.found && !extracted.plotNumber.conflict ? docNormalizeKey(extracted.plotNumber.display) : '';
    var nameKey = extracted.ownerName.found && !extracted.ownerName.conflict ? docNormalizeKey(extracted.ownerName.display) : '';
    var cnicDigits = extracted.cnic.found && !extracted.cnic.conflict ? extracted.cnic.value : '';
    var best = null, bestScore = 0;
    (properties||[]).forEach(function(p){
      var score = 0;
      var pPlot = docNormalizeKey(p.plot), pOwner = docNormalizeKey(p.owner);
      var pCnic = p.cnic ? p.cnic.replace(/[^\d]/g,'') : '';
      if(plotKey && pPlot.indexOf(plotKey)!==-1) score += 2;
      if(nameKey && pOwner === nameKey) score += 2;
      if(cnicDigits && pCnic && pCnic === cnicDigits) score += 3;
      if(score > bestScore){ bestScore = score; best = p; }
    });
    return bestScore >= 2 ? {property:best, score:bestScore} : {property:null, score:bestScore};
  }

  // Compares extracted fields against ONE specific property record.
  // Returns per-field match/mismatch/conflict/unknown plus a flat list of
  // plain-language mismatch reasons and self-declared-status flags.
  function compareToProperty(extracted, property, opts){
    opts = opts || {};
    var result = {name:'unknown', cnic:'unknown', plot:'unknown', survey:'unknown', address:'unknown', approvedArea:'unknown', paymentStatus:'unknown', details:{}, mismatches:[], flags:[], uncertain:[]};
    if(!property) return result;
    var profile = extracted.profile || TYPE_PROFILES.other;
    var uses = function(f){ return profile.fields.indexOf(f) !== -1; };

    if(uses('name')){
      if(extracted.ownerName.conflict){ result.name='conflict'; result.details.name={extracted:extracted.ownerName.values, record:property.owner}; }
      else if(extracted.ownerName.found){
        var nm = docNormalizeKey(extracted.ownerName.display)===docNormalizeKey(property.owner);
        result.name = nm?'match':'mismatch';
        result.details.name = {extracted:extracted.ownerName.display, record:property.owner};
        if(!nm) result.mismatches.push('Name in document ("'+extracted.ownerName.display+'") does not match the recorded owner ("'+property.owner+'").');
      }
    }
    if(uses('cnic')){
      if(extracted.cnic.conflict){ result.cnic='conflict'; }
      else if(extracted.cnic.found && property.cnic){
        var cm = extracted.cnic.value === property.cnic.replace(/[^\d]/g,'');
        var cUnc = !cm && opts.ocr && ocrConfusable(extracted.cnic.value, property.cnic.replace(/[^\d]/g,''));
        result.cnic = cm?'match':cUnc?'uncertain':'mismatch';
        result.details.cnic = {extracted:extracted.cnic.display, record:property.cnic};
        if(cUnc) result.uncertain.push('CNIC read from the image ("'+extracted.cnic.display+'") differs from the record only in characters OCR commonly misreads, so it cannot be called a mismatch.');
        else if(!cm) result.mismatches.push('CNIC in document does not match the CNIC on record for this property.');
      }
    }
    if(uses('plot')){
      if(extracted.plotNumber.conflict){ result.plot='conflict'; }
      else if(extracted.plotNumber.found){
        var pm = fuzzyContains(property.plot, extracted.plotNumber.display);
        var pUnc = !pm && opts.ocr && confusionKey(property.plot).indexOf(confusionKey(extracted.plotNumber.display))!==-1;
        result.plot = pm?'match':pUnc?'uncertain':'mismatch';
        result.details.plot = {extracted:extracted.plotNumber.display, record:property.plot};
        if(pUnc) result.uncertain.push('Plot number read from the image ("'+extracted.plotNumber.display+'") differs from the record ("'+property.plot+'") only in characters OCR commonly misreads, so it cannot be called a mismatch.');
        else if(!pm) result.mismatches.push('Plot number in document ("'+extracted.plotNumber.display+'") does not match the recorded plot ("'+property.plot+'").');
      }
    }
    if(uses('survey') && property.survey){
      if(extracted.surveyNumber.conflict){ result.survey='conflict'; }
      else if(extracted.surveyNumber.found){
        var sm = fuzzyContains(property.survey, extracted.surveyNumber.display);
        result.survey = sm?'match':'mismatch';
        result.details.survey = {extracted:extracted.surveyNumber.display, record:property.survey};
        if(!sm) result.mismatches.push('Survey number in document ("'+extracted.surveyNumber.display+'") does not match the recorded survey number ("'+property.survey+'").');
      }
    }
    if(uses('address') && property.address){
      if(extracted.address.found){
        var exK = docNormalizeKey(extracted.address.display), rcK = docNormalizeKey(property.address);
        var am = exK.length >= rcK.length*0.8 && (exK.indexOf(rcK)!==-1 || rcK.indexOf(exK)!==-1);
        result.address = am?'match':'mismatch';
        result.details.address = {extracted:extracted.address.display, record:property.address};
        if(!am) result.mismatches.push('Property address in document ("'+extracted.address.display+'") does not match the recorded address ("'+property.address+'").');
      }
    }
    if(uses('approvedArea') && property.size){
      if(extracted.approvedArea.found){
        var numOf = function(v){ var m=(v||'').match(/\d[\d,]*(?:\.\d+)?/); return m?parseFloat(m[0].replace(/,/g,'')):NaN; };
        var recordNum = numOf(property.size), docNum = numOf(extracted.approvedArea.display);
        var areaOk = isNaN(recordNum) || isNaN(docNum) ? true : docNum <= recordNum;
        result.approvedArea = areaOk?'match':'mismatch';
        result.details.approvedArea = {extracted:extracted.approvedArea.display, record:property.size};
        if(!areaOk) result.mismatches.push('Approved area in document ("'+extracted.approvedArea.display+'") exceeds the recorded property size ("'+property.size+'").');
      }
    }
    if(uses('paymentStatus') && extracted.paymentStatus.found){
      if(SUSPICIOUS_STATUS_WORDS.test(extracted.paymentStatus.display)){
        result.paymentStatus = 'flagged';
        result.mismatches.push('Payment status stated in the document ("'+extracted.paymentStatus.display+'") indicates a discrepancy with the record (the document itself reports a problem).');
      } else { result.paymentStatus = 'ok'; }
    }
    return result;
  }


  // Shared decision rules (used by domain/documentVerification.js AND scripts/manifest-report.mjs so
  // the tests exercise the exact logic the app runs).
  var FIELD_KEY = {name:'ownerName', cnic:'cnic', plot:'plotNumber', survey:'surveyNumber', address:'address', approvedArea:'approvedArea', paymentStatus:'paymentStatus'};
  function decide(extraction, property, opts){
    opts = opts || {};
    var conflicts = ['ownerName','plotNumber','cnic','surveyNumber'].filter(function(f){ return extraction[f] && extraction[f].conflict; });
    if(conflicts.length) return {status:'suspicious', reasons:['The document contains more than one different value for: '+conflicts.join(', ')+'. This is an inconsistency inside the document itself.'], cmp:null};
    var profile = extraction.profile;
    var missing = profile.fields.filter(function(f){ if(f==='paymentStatus') return false; var k=FIELD_KEY[f]; return !extraction[k].found; });
    var anyFound = profile.fields.some(function(f){ return extraction[FIELD_KEY[f]].found; });
    if(!anyFound) return {status:'unable_to_verify', reasons:['No usable information could be extracted from the document.'], cmp:null};
    var cmp = compareToProperty(extraction, property, opts);
    if(cmp.mismatches.length) return {status:'not_verified', reasons:cmp.mismatches, cmp:cmp};
    if(missing.length) return {status:'unable_to_verify', reasons:['Required field(s) not detected: '+missing.join(', ')+'. Verification could not be completed.'], cmp:cmp};
    if(cmp.uncertain.length) return {status:'unable_to_verify', reasons:cmp.uncertain, cmp:cmp};
    return {status:'verified', reasons:[], cmp:cmp};
  }

  var Extraction = {
    TYPE_PROFILES: TYPE_PROFILES,
    scanTokens: scanTokens,
    extractByRole: extractByRole,
    extractOwnerName: extractOwnerName,
    extractPlotNumber: extractPlotNumber,
    extractCNIC: extractCNIC,
    detectDocumentType: detectDocumentType,
    parseDocumentText: parseDocumentText,
    matchProperty: matchProperty,
    compareToProperty: compareToProperty,
    decide: decide,
    docNormalizeKey: docNormalizeKey,
    _internal: {normalizeCnicCandidate:normalizeCnicCandidate, normalizePlotCandidate:normalizePlotCandidate, normalizeNameCandidate:normalizeNameCandidate, isStopwordOnly:isStopwordOnly}
  };

export default Extraction;
