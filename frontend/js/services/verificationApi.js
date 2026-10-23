/* Client for POST /api/v1/verification/check. The server answers match / mismatch /
 * unable_to_verify only; owner names never reach the browser. */
import { VERIFY_API_URL } from '../config.js';
import { AppError } from '../core/errors.js';
import { fetchJson } from './http.js';

const VERDICTS = ['match', 'mismatch', 'unable_to_verify'];

/** @param {string} propertyId @param {string} ownerName @returns {Promise<{result:string,note:string}>} */
export async function checkOwnerName(propertyId, ownerName) {
  const { ok, status, data } = await fetchJson(VERIFY_API_URL, { method: 'POST', body: { property_id: propertyId, owner_name: ownerName } });
  if (data === null) throw new AppError(`The verification service returned an unexpected response (HTTP ${status}).`, { code: 'non_json' });
  if (!ok) throw new AppError(data.error || 'The check could not be completed.', { code: data.code || 'http_error' });
  if (!VERDICTS.includes(data.result)) throw new AppError('The verification service returned an unknown result.', { code: 'bad_result' });
  return data;
}
