import type { OwnedDetail, PrivateItemInput } from '../../api/m4';
import { fieldValueText } from '../../api/detail';
import { checkItemDate, itemDateText, type DayEdge } from '../../lib/itemDates';
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
  // The stored instant when the answer has it (keeps a typed time), else the row's date.
  const when = (name: string, fallback: string | null | undefined, edge: DayEdge) => {
    const f = item.detail.fields.find((x) => x.name === name);
    const v = typeof f?.value === 'string' ? f.value : fallback;
    return v ? itemDateText(v, edge) : '';
  };
  return {
    stream: item.stream,
    title: item.title,
    organisation: field('organisation'),
    deadline: event ? '' : when('deadlineAt', item.deadline, 'end'),
    eventStart: event ? when('eventStart', item.eventDates?.start, 'start') : '',
    eventEnd: event && end && end !== item.eventDates?.start ? when('eventEnd', end, 'end') : '',
    // The API sends the amount as a decimal string ("6000000.00"); the form takes whole numbers.
    value: wholeAmount(field('valueAmount')),
    currency: field('valueCurrency') || 'RWF',
    location: field('location') || (item.detail.location ?? ''),
    url: item.detail.originalUrl ?? '',
    notes: item.detail.note ?? '',
  };
}

function wholeAmount(text: string): string {
  const m = text.trim().match(/^(\d+)(?:\.0+)?$/);
  return m ? m[1]! : text;
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

/** A typed date the API will take: with its year (spec 2.5), understood, in the plausible window. */
function dateError(raw: string, edge: DayEdge): string | undefined {
  const d = checkItemDate(raw, edge);
  if (!('problem' in d)) return undefined;
  return d.problem === 'out_of_window' ? ITEM_ERRORS.dateRange : ITEM_ERRORS.date;
}

/** What the API is sent for a typed date ("2026-12-07", "2026-12-07T17:00"); null when empty. */
function dateValue(raw: string, edge: DayEdge): string | null {
  if (!raw.trim()) return null;
  const d = checkItemDate(raw.trim(), edge);
  return 'problem' in d ? raw.trim() : d.value;
}

export function validate(f: ItemForm): ItemErrors {
  const e: ItemErrors = {};
  if (!f.stream) e.stream = ITEM_ERRORS.stream;
  if (!f.title.trim()) e.title = ITEM_ERRORS.title;
  if (f.stream === 'event') {
    if (!f.eventStart.trim()) {
      if (f.eventEnd.trim()) e.eventStart = ITEM_ERRORS.eventStart;
    } else {
      const err = dateError(f.eventStart.trim(), 'start');
      if (err) e.eventStart = err;
    }
    if (f.eventEnd.trim()) {
      const err = dateError(f.eventEnd.trim(), 'end');
      if (err) e.eventEnd = err;
      else if (!e.eventStart && f.eventStart.trim()) {
        // As the API compares them: the end (end of its day, unless timed) before the start.
        const start = checkItemDate(f.eventStart.trim(), 'start');
        const end = checkItemDate(f.eventEnd.trim(), 'end');
        if (!('problem' in start) && !('problem' in end) && end.at < start.at) e.eventEnd = ITEM_ERRORS.eventEnd;
      }
    }
  } else if (f.deadline.trim()) {
    const err = dateError(f.deadline.trim(), 'end');
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
    deadline: event ? null : dateValue(f.deadline, 'end'),
    eventStart: event ? dateValue(f.eventStart, 'start') : null,
    eventEnd: event ? dateValue(f.eventEnd, 'end') : null,
    value: value ? Number(value) : null,
    currency: value ? f.currency.trim().toUpperCase() : null,
    location: text(f.location),
    url: text(f.url),
    notes: text(f.notes),
  };
}
