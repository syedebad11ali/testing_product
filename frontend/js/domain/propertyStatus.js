/* domain/propertyStatus.js — Rolls a property's individual checks up into one overall status. */
import { CATS } from '../data/properties.js';

export function overallStatus(p){
  const vals = CATS.map(c=>p.verification[c[0]].status);
  if(vals.includes('issue')) return 'issue';
  if(vals.includes('review')) return 'review';
  if(vals.every(v=>v==='verified')) return 'verified';
  return 'unchecked';
}

