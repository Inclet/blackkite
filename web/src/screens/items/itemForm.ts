import type { OwnedDetail, PrivateItemInput } from '../../api/m4';
import { fieldValueText } from '../../api/detail';
import { kigaliToday } from '../../lib/deadline';
import type { Stream } from '../../lib/streams';

/** The "Add an item" form as typed (strings), before it becomes a POST /api/items body. */
export interface ItemForm {
  stream: Stream | null;
  title: string;
  organisation: string;
  deadline: string;
  eventStart: string;
  eventEnd: string;
  value: string;
  /** Three letters; RWF, USD and EUR are offered as chips. */
  currency: string;
  location: string;
  url: string;
  notes: string;
}

export type ItemErrors = Partial<Record<keyof ItemForm, string>>;

/** Field errors, in the profile editor's voice. Not on any board (design review). */
export const ITEM_ERRORS = {
  stream: 'Choose what kind of item this is.',
  title: 'Give it a title.',
  date: 'Use a full date with the year, such as 7 Dec 2026.',
  dateRange: 'Use a date between a year ago and two years from now.',
  eventStart: 'Add the day it starts.',
  eventEnd: 'Make this the same day as the start or later.',
  value: 'Use a whole number, such as 5000000.',
  url: 'Use a web address that starts with https:// or http://.',
} as const;

export function emptyForm(): ItemForm {
  return { stream: null, title: '', organisation: '', deadline: '', eventStart: '', eventEnd: '', value: '', currency: 'RWF', location: '', url: '', notes: '' };
}

/** The form for editing the owner's item, from GET /api/opportunities/{id} (the API keeps no separate copy of what was typed). */
export function toForm(item: OwnedDetail): ItemForm {
  const field = (name: string) => {
    const f = item.detail.fields.find((x) => x.name === name);
    return f === undefined || f.value === null ? '' : fieldValueText(f.value);
  };
  const event = item.stream === 'event';
  const end = item.eventDates?.end;
  return {
    stream: item.stream,
    title: item.title,
    organisation: field('organisation'),
    deadline: event ? '' : (item.deadline ?? ''),
    eventStart: event ? (item.eventDates?.start ?? '') : '',
    eventEnd: event && end && end !== item.eventDates?.start ? end : '',
    value: field('valueAmount'),
    currency: field('valueCurrency') || 'RWF',
    location: field('location') || (item.detail.location ?? ''),
    url: item.detail.originalUrl ?? '',
    notes: item.detail.note ?? '',
  };
}

/** Map the API's refused fields (RefusalOut errors, camelCase) onto the form. */
export function serverErrors(errors: { field: string | null; message: string }[]): ItemErrors {
  const keys = new Set(Object.keys(emptyForm()));
  const out: ItemErrors = {};
  for (const e of errors) {
    if (!e.field || !keys.has(e.field) || out[e.field as keyof ItemForm]) continue;
    const m = e.message.trim();
    out[e.field as keyof ItemForm] = `${m.charAt(0).toUpperCase()}${m.slice(1)}${/[.!?]$/.test(m) ? '' : '.'}`;
  }
  return out;
}

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;

/** An explicit, real calendar date with its year (spec 2.5: every date needs a year), in a plausible window. */
function dateError(raw: string): string | undefined {
  const m = raw.match(ISO_DATE);
  if (!m) return ITEM_ERRORS.date;
  const [y, mo, d] = [Number(m[1]), Number(m[2]), Number(m[3])];
  const date = new Date(Date.UTC(y, mo - 1, d));
  if (date.getUTCMonth() !== mo - 1 || date.getUTCDate() !== d) return ITEM_ERRORS.date;
  // The API's plausible window (pipeline validate): a year back, two years ahead.
  const today = kigaliToday();
  const back = `${Number(today.slice(0, 4)) - 1}${today.slice(4)}`;
  const ahead = `${Number(today.slice(0, 4)) + 2}${today.slice(4)}`;
  if (raw < back || raw > ahead) return ITEM_ERRORS.dateRange;
  return undefined;
}

export function validate(f: ItemForm): ItemErrors {
  const e: ItemErrors = {};
  if (!f.stream) e.stream = ITEM_ERRORS.stream;
  if (!f.title.trim()) e.title = ITEM_ERRORS.title;
  if (f.stream === 'event') {
    if (!f.eventStart.trim()) {
      if (f.eventEnd.trim()) e.eventStart = ITEM_ERRORS.eventStart;
    } else {
      const err = dateError(f.eventStart.trim());
      if (err) e.eventStart = err;
    }
    if (f.eventEnd.trim()) {
      const err = dateError(f.eventEnd.trim());
      if (err) e.eventEnd = err;
      else if (!e.eventStart && f.eventStart.trim() && f.eventEnd.trim() < f.eventStart.trim()) e.eventEnd = ITEM_ERRORS.eventEnd;
    }
  } else if (f.deadline.trim()) {
    const err = dateError(f.deadline.trim());
    if (err) e.deadline = err;
  }
  const value = f.value.trim().replace(/[ ,]/g, '');
  if (value && !/^\d+$/.test(value)) e.value = ITEM_ERRORS.value;
  const url = f.url.trim();
  if (url) {
    let ok = false;
    try {
      const u = new URL(url);
      ok = (u.protocol === 'https:' || u.protocol === 'http:') && u.hostname.includes('.');
    } catch {
      ok = false;
    }
    if (!ok) e.url = ITEM_ERRORS.url;
  }
  return e;
}

const text = (s: string) => (s.trim() ? s.trim() : null);

/**
 * The body POST /api/items and PATCH /api/items/{id} take. Empty fields are null
 * (PATCH clears them). An event sends its dates, anything else its deadline.
 */
export function toInput(f: ItemForm): PrivateItemInput {
  const value = f.value.trim().replace(/[ ,]/g, '');
  const event = f.stream === 'event';
  return {
    stream: f.stream!,
    title: f.title.trim(),
    organisation: text(f.organisation),
    deadline: event ? null : text(f.deadline),
    eventStart: event ? text(f.eventStart) : null,
    eventEnd: event ? text(f.eventEnd) : null,
    value: value ? Number(value) : null,
    currency: value ? f.currency.trim().toUpperCase() : null,
    location: text(f.location),
    url: text(f.url),
    notes: text(f.notes),
  };
}
