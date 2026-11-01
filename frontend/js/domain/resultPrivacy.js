/* domain/resultPrivacy.js — Pure helpers that keep identifiers out of stored or displayed verification results. No imports, so the
   state store can use it without an import cycle. */
export function maskCnic(digits){
  if(!digits || digits.length!==13) return digits || '';
  return digits.slice(0,5)+'-******'+digits.slice(11,12)+'-'+digits.slice(12);
}

/* The result is kept in browser storage (history). Full CNICs must not be persisted there: this returns a copy in which every
   13-digit CNIC (extracted values, conflict lists, per-role buckets, entered fields) is masked. Display code masks CNICs again. */
function maskCnicLike(v){
  if(typeof v !== 'string') return v;
  const digits = v.replace(/[^\d]/g,'');
  return digits.length===13 ? maskCnic(digits) : v;
}
export function sanitizeResultForStorage(result){
  if(!result || typeof result !== 'object') return result;
  const copy = JSON.parse(JSON.stringify(result));
  const maskField = f => { if(f && typeof f === 'object'){ f.value = maskCnicLike(f.value); f.display = maskCnicLike(f.display); if(Array.isArray(f.values)) f.values = f.values.map(maskCnicLike); } };
  if(copy.extraction){
    maskField(copy.extraction.cnic);
    const roles = copy.extraction.allRoles && copy.extraction.allRoles.cnic;
    if(roles) Object.keys(roles).forEach(k => maskField(roles[k]));
  }
  if(copy.fields) copy.fields.cnic = maskCnicLike(copy.fields.cnic);
  if(Array.isArray(copy.checks)) copy.checks.forEach(c => { if(c && typeof c.text === 'string') c.text = c.text.replace(/\b\d{5}-?\d{7}-?\d\b/g, m => maskCnicLike(m)); });
  // Message text (reasons, limitations) can quote a value read from the document, so it is masked the same way before storage.
  ['reasons','limitations'].forEach(k => { if(Array.isArray(copy[k])) copy[k] = copy[k].map(t => typeof t === 'string' ? t.replace(/\b\d{5}-?\d{7}-?\d\b/g, m => maskCnicLike(m)) : t); });
  return copy;
}
