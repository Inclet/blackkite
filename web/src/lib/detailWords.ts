import type { ExtractedField, OpportunityChange } from '../api/types';
import { formatTime } from './calendar';

const TIMEZONE = 'Africa/Kigali';

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const ISO_DATE_TIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/;

/** "7 Dec 2026": full dates, with the year. */
export function formatFullDate(isoDate: string): string {
  const [y, m, d] = isoDate.slice(0, 10).split('-').map(Number);
  return new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(new Date(Date.UTC(y!, m! - 1, d!)));
}

/** "30 Nov 2026, 5pm" in Kigali time; midnight is left as the date alone. Dates without a time as "30 Nov 2026". */
export function formatWhen(value: string): string {
  if (ISO_DATE.test(value)) return formatFullDate(value);
  if (!ISO_DATE_TIME.test(value)) return value;
  const at = new Date(value);
  if (Number.isNaN(at.getTime())) return value;
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: TIMEZONE, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(at);
  const get = (t: string) => parts.find((p) => p.type === t)!.value;
  const date = formatFullDate(`${get('year')}-${get('month')}-${get('day')}`);
  const time = `${get('hour')}:${get('minute')}`;
  return time === '00:00' ? date : `${date}, ${formatTime(time)}`;
}

/** Amounts as the digest writes them: "FRW 120,000,000". */
export function formatAmount(amount: number, currency?: string | null): string {
  const n = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 2 }).format(amount);
  const c = !currency || currency === 'RWF' ? 'FRW' : currency;
  return `${c} ${n}`;
}

/** Labels for the extracted fields (spec 6), in the order the Details section lists them. */
export const FIELD_LABELS: Record<string, string> = {
  organisation: 'Organisation',
  deadlineAt: 'Deadline',
  eventStart: 'Starts',
  eventEnd: 'Ends',
  publishedAt: 'Published',
  valueAmount: 'Value',
  valueNote: 'About the value',
  location: 'Location',
  eligibility: 'Who can apply',
  requirements: 'Requirements',
  submissionMethod: 'How to apply',
  fees: 'Fees',
  subtype: 'Kind',
  summary: 'Summary',
};

const DATE_FIELDS = new Set(['deadlineAt', 'eventStart', 'eventEnd', 'publishedAt']);

function camel(name: string): string {
  return name.replace(/_([a-z])/g, (_, c: string) => c.toUpperCase());
}

/** A field name as words: the label, else the name split up ("submission_method" → "Submission method"). */
export function fieldLabel(name: string): string {
  const key = camel(name);
  if (FIELD_LABELS[key]) return FIELD_LABELS[key];
  const words = key.replace(/([A-Z])/g, ' $1').trim().toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export interface DetailLine {
  name: string;
  label: string;
  /** One value, or one per requirement. */
  values: { text: string; quotes: string[] }[];
}

function valueText(name: string, value: unknown, currency?: string | null): string {
  if (name === 'valueAmount' && typeof value === 'number') return formatAmount(value, currency);
  if (DATE_FIELDS.has(name) && typeof value === 'string') return formatWhen(value);
  if (Array.isArray(value)) return value.join('; ');
  return String(value);
}

/**
 * The Details section: each extracted field with the passages behind it, in a
 * fixed order. The currency joins the amount; requirements pair with their snippets.
 */
export function detailLines(fields: ExtractedField[]): DetailLine[] {
  const by = new Map(fields.map((f) => [camel(f.name), f]));
  const currency = by.get('valueCurrency')?.value;
  const order = [...Object.keys(FIELD_LABELS), ...[...by.keys()].filter((k) => !(k in FIELD_LABELS) && k !== 'valueCurrency' && k !== 'title')];
  const out: DetailLine[] = [];
  for (const name of order) {
    const f = by.get(name);
    if (!f || f.value === null || f.value === '' || (Array.isArray(f.value) && f.value.length === 0)) continue;
    if (name === 'requirements' && Array.isArray(f.value)) {
      const snippets = f.snippets ?? [];
      out.push({ name, label: fieldLabel(name), values: f.value.map((v, i) => ({ text: String(v), quotes: snippets[i] ? [snippets[i]!] : [] })) });
      continue;
    }
    const quotes = f.snippets?.length ? f.snippets : f.snippet ? [f.snippet] : [];
    out.push({ name, label: fieldLabel(name), values: [{ text: valueText(name, f.value, typeof currency === 'string' ? currency : null), quotes }] });
  }
  return out;
}

const STATUS_WORDS: Record<string, string> = {
  open: 'open',
  closing_soon: 'closing soon',
  expired: 'closed',
  awarded: 'awarded',
  cancelled: 'cancelled',
};

function changeValue(field: string, v: unknown): string {
  if (v === null || v === undefined || v === '') return 'nothing';
  if (field === 'status' && typeof v === 'string') return STATUS_WORDS[v] ?? v;
  if (typeof v === 'string' && (ISO_DATE.test(v) || ISO_DATE_TIME.test(v))) return formatWhen(v);
  if (typeof v === 'number' && field === 'valueAmount') return formatAmount(v);
  if (Array.isArray(v)) return v.join('; ');
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

/** One change event in plain words: "20 Nov 2026: the deadline moved from 28 Nov 2026, 5pm to 30 Nov 2026, 5pm." */
export function changeSentence(change: OpportunityChange): string {
  const field = camel(change.field);
  const when = formatWhen(change.at).replace(/, .*$/, '');
  const empty = (v: unknown) => v === null || v === undefined || v === '';
  let what: string;
  const visibility = (v: unknown) => (v !== null && typeof v === 'object' ? (v as { visibility?: unknown }).visibility : v);
  if (field === 'visibility' && visibility(change.new) === 'public') what = 'an admin made it public, with the owner’s consent';
  else if (field === 'deadlineAt') {
    if (empty(change.old)) what = `a deadline was added: ${changeValue(field, change.new)}`;
    else if (empty(change.new)) what = 'the deadline was removed';
    else what = `the deadline moved from ${changeValue(field, change.old)} to ${changeValue(field, change.new)}`;
  } else if (field === 'needsReview') {
    what = change.new ? 'it was flagged for a person to check' : 'a person checked it';
  } else {
    const label = fieldLabel(field).toLowerCase();
    if (empty(change.old)) what = `the ${label} was added: ${changeValue(field, change.new)}`;
    else if (empty(change.new)) what = `the ${label} was removed`;
    else what = `the ${label} changed from ${changeValue(field, change.old)} to ${changeValue(field, change.new)}`;
  }
  return `${when}: ${what}.`;
}
