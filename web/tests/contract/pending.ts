/**
 * Contract changes the API track is making in parallel (docs/api-contract.md at
 * 3f9c3f7), laid over api-schemas.json until it is regenerated at merge.
 *
 * Each patch applies only while the dumped file still has the old shape, so once
 * `npm run contract:schemas` writes the new file every patch is a no-op and the
 * tests check against the API's own models. `pendingPatches(dump)` names the
 * patches still applied; the stub contract test lists them, and once it is empty
 * this file can go.
 *
 * - DigestSettingsIn / DigestSettingsOut: `alertThreshold` (0-100) becomes
 *   `alertMinFit`: "strong" | "good" | null.
 * - FeedItem (and FeedContent's items, OpportunityOut): `provisional: boolean`, always sent.
 * - StateIn (PUT /opportunities/{id}/state): `dismissReason` is one of five codes.
 *   The current file has no StateIn at all (dump_schemas.py now asks for it).
 * - FeedUser.name is "" when the user has no name: same schema (a string), no patch.
 */
import type { Schema } from './schemaCheck';

export const DISMISS_REASON_CODES = ['not_my_sector', 'too_small', 'cant_meet_requirements', 'already_knew', 'other'] as const;

const ALERT_MIN_FIT: Schema = { anyOf: [{ enum: ['strong', 'good'], type: 'string' }, { type: 'null' }], title: 'Alertminfit' };
const PROVISIONAL: Schema = { title: 'Provisional', type: 'boolean' };
const STATE_IN: Schema = {
  title: 'StateIn',
  type: 'object',
  additionalProperties: false,
  properties: {
    state: { enum: ['unseen', 'saved', 'dismissed', 'acting', 'done'], title: 'State', type: 'string' },
    dismissReason: { anyOf: [{ enum: [...DISMISS_REASON_CODES], type: 'string' }, { type: 'null' }], title: 'Dismissreason' },
  },
  required: ['state'],
};

interface Dump {
  schemas: Record<string, Schema>;
}

function alertMinFit(s: Schema | undefined, out: boolean): boolean {
  if (!s?.properties || 'alertMinFit' in s.properties) return false;
  delete s.properties.alertThreshold;
  s.properties.alertMinFit = out ? ALERT_MIN_FIT : { ...ALERT_MIN_FIT, default: null } as Schema;
  if (s.required) s.required = s.required.map((k) => (k === 'alertThreshold' ? 'alertMinFit' : k));
  return true;
}

function provisional(s: Schema | undefined): boolean {
  if (!s?.properties || 'provisional' in s.properties) return false;
  s.properties.provisional = PROVISIONAL;
  s.required = [...(s.required ?? []), 'provisional'];
  return true;
}

/** A deep copy of the dump with the pending patches applied, and their names. */
export function withPending(dump: Dump): { schemas: Record<string, Schema>; applied: string[] } {
  const schemas = structuredClone(dump.schemas);
  const applied: string[] = [];
  if (alertMinFit(schemas.DigestSettingsIn, false)) applied.push('DigestSettingsIn.alertMinFit');
  if (alertMinFit(schemas.DigestSettingsOut, true)) applied.push('DigestSettingsOut.alertMinFit');
  if (provisional(schemas.FeedItem)) applied.push('FeedItem.provisional');
  if (provisional(schemas.FeedContent?.$defs?.FeedItem)) applied.push('FeedContent.items[].provisional');
  if (provisional(schemas.OpportunityOut)) applied.push('OpportunityOut.provisional');
  if (!schemas.StateIn) {
    schemas.StateIn = STATE_IN;
    applied.push('StateIn');
  }
  return { schemas, applied };
}
