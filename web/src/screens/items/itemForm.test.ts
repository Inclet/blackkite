import { afterEach, beforeEach, expect, test } from 'vitest';
import { setNowForTests } from '../../lib/now';
import { changedInput, emptyForm, ITEM_ERRORS, serverErrors, toForm, toInput, validate } from './itemForm';
import type { OwnedDetail } from '../../api/m4';

beforeEach(() => setNowForTests('2026-11-24T14:00:00+02:00'));
afterEach(() => setNowForTests(null));

const base = { ...emptyForm(), stream: 'tender' as const, title: 'Fuel supply' };

test('stream and title are needed; everything else may stay empty', () => {
  expect(validate(emptyForm())).toEqual({ stream: ITEM_ERRORS.stream, title: ITEM_ERRORS.title });
  expect(validate(base)).toEqual({});
});

test('dates: typed with the year in the forms the API reads, in its plausible window', () => {
  for (const d of ['2026-12-07', '7 Dec 2026', '07/12/2026', '7 Dec 2026, 5pm', '7 Dec 2026 17:00']) expect(validate({ ...base, deadline: d })).toEqual({});
  expect(validate({ ...base, deadline: '7 Dec' }).deadline).toBe(ITEM_ERRORS.date);
  expect(validate({ ...base, deadline: 'soon' }).deadline).toBe(ITEM_ERRORS.date);
  expect(validate({ ...base, deadline: '30 Feb 2026' }).deadline).toBe(ITEM_ERRORS.date);
  // The API's window: a year back, two years ahead (now 24 Nov 2026, 2pm), deadlines at the end of their day.
  expect(validate({ ...base, deadline: '23 Nov 2025' }).deadline).toBe(ITEM_ERRORS.dateRange);
  expect(validate({ ...base, deadline: '24 Nov 2025' })).toEqual({});
  expect(validate({ ...base, deadline: '22 Nov 2028' })).toEqual({});
  expect(validate({ ...base, deadline: '24 Nov 2028' }).deadline).toBe(ITEM_ERRORS.dateRange);
});

test('events: an end needs a start, and not before it', () => {
  const ev = { ...base, stream: 'event' as const };
  expect(validate({ ...ev, eventEnd: '2 Dec 2026' }).eventStart).toBe(ITEM_ERRORS.eventStart);
  expect(validate({ ...ev, eventStart: '3 Dec 2026', eventEnd: '2 Dec 2026' }).eventEnd).toBe(ITEM_ERRORS.eventEnd);
  expect(validate({ ...ev, eventStart: '1 Dec 2026', eventEnd: '02/12/2026' })).toEqual({});
  // Same day: an end with no time is the end of the day; a timed end before a timed start is refused.
  expect(validate({ ...ev, eventStart: '1 Dec 2026, 9am', eventEnd: '1 Dec 2026' })).toEqual({});
  expect(validate({ ...ev, eventStart: '1 Dec 2026, 5pm', eventEnd: '1 Dec 2026, 9am' }).eventEnd).toBe(ITEM_ERRORS.eventEnd);
});

test('value is a whole number; links are http(s) only', () => {
  expect(validate({ ...base, value: '5,000,000' })).toEqual({});
  expect(validate({ ...base, value: '5m' }).value).toBe(ITEM_ERRORS.value);
  expect(validate({ ...base, url: 'javascript:alert(1)' }).url).toBe(ITEM_ERRORS.url);
  expect(validate({ ...base, url: 'ftp://x.rw/a' }).url).toBe(ITEM_ERRORS.url);
  expect(validate({ ...base, url: 'https://example.rw/notice' })).toEqual({});
});

test('the body: empty fields null, deadline or event dates by stream, currency only with a value', () => {
  expect(toInput({ ...base, deadline: '7 Dec 2026', eventStart: '1 Dec 2026', value: '5,000,000', currency: 'USD', notes: '  call Tuesday ' })).toEqual({
    stream: 'tender',
    title: 'Fuel supply',
    organisation: null,
    deadline: '2026-12-07',
    eventStart: null,
    eventEnd: null,
    value: 5000000,
    currency: 'USD',
    location: null,
    url: null,
    notes: 'call Tuesday',
  });
  const ev = toInput({ ...base, stream: 'event', deadline: '7 Dec 2026', eventStart: '01/12/2026 9:30am', eventEnd: '2 Dec 2026' });
  expect([ev.deadline, ev.eventStart, ev.eventEnd, ev.currency]).toEqual([null, '2026-12-01T09:30', '2026-12-02', null]);
  expect(toInput({ ...base, deadline: '7 Dec 2026, 5pm' }).deadline).toBe('2026-12-07T17:00');
});

test('the edit form comes from the opportunity answer', () => {
  const item = {
    id: 'own-1',
    stream: 'event',
    title: 'Expo',
    organisation: 'RDB',
    fit: null,
    deadline: null,
    eventDates: { start: '2026-12-01', end: '2026-12-02' },
    state: 'unseen',
    provisional: false,
    detail: {
      reasons: [],
      trust: { state: 'unconfirmed', desktop: '', phone: '' },
      originalUrl: 'https://x.rw/e',
      fields: [
        { name: 'organisation', value: 'RDB' },
        { name: 'valueAmount', value: 2000000 },
        { name: 'valueCurrency', value: 'KES' },
        { name: 'location', value: 'Kigali' },
      ],
      sources: [],
      documents: [],
      changes: [],
      note: 'Bring cards',
      state: 'unseen',
      ownItem: { shareConsent: false, published: false },
    },
  } as unknown as OwnedDetail;
  expect(toForm(item)).toEqual({
    stream: 'event',
    title: 'Expo',
    organisation: 'RDB',
    deadline: '',
    eventStart: '1 Dec 2026',
    eventEnd: '2 Dec 2026',
    value: '2000000',
    currency: 'KES',
    location: 'Kigali',
    url: 'https://x.rw/e',
    notes: 'Bring cards',
  });
});

test('refused fields from the API land on the form', () => {
  expect(serverErrors([{ field: 'deadline', message: 'include the year, for example 30 Nov 2026' }, { field: null, message: 'x' }, { field: 'config.x', message: 'y' }])).toEqual({
    deadline: 'Include the year, for example 30 Nov 2026.',
  });
});

test('the edit form shows stored dates as typed text, keeping a time', () => {
  const item = {
    id: 'own-2',
    stream: 'tender',
    title: 'Fuel supply',
    organisation: '',
    fit: null,
    deadline: '2026-12-07',
    state: 'unseen',
    provisional: false,
    detail: { reasons: [], trust: { state: 'unconfirmed', desktop: '', phone: '' }, originalUrl: '', fields: [{ name: 'deadlineAt', value: '2026-12-07T17:00:00+02:00' }], sources: [], documents: [], changes: [], note: null, state: 'unseen' },
  } as unknown as OwnedDetail;
  expect(toForm(item).deadline).toBe('7 Dec 2026, 5pm');
  expect(toForm({ ...item, detail: { ...item.detail, fields: [{ name: 'deadlineAt', value: '2026-12-07T23:59:59+02:00' }] } }).deadline).toBe('7 Dec 2026');
  expect(toForm({ ...item, detail: { ...item.detail, fields: [] } }).deadline).toBe('7 Dec 2026');
  expect(toInput(toForm(item)).deadline).toBe('2026-12-07T17:00');
});

test('the edit form takes the API amount (a decimal string) as a whole number', () => {
  const item = {
    id: 'own-3', stream: 'tender', title: 'Fuel', organisation: '', fit: null, deadline: null, state: 'unseen', provisional: false,
    detail: { reasons: [], trust: { state: 'unconfirmed', desktop: '', phone: '' }, originalUrl: '', fields: [{ name: 'valueAmount', value: '6000000.00', display: 'FRW 6,000,000' }], sources: [], documents: [], changes: [], note: null, state: 'unseen' },
  } as unknown as OwnedDetail;
  expect(toForm(item).value).toBe('6000000');
  expect(validate(toForm(item))).toEqual({});
});

/** An owned item as GET /api/opportunities/{id} answers it: the row's Kigali dates plus the stored instants in fields. */
function stored(stream: 'tender' | 'event', rowDates: Record<string, unknown>, fields: { name: string; value: unknown }[]): OwnedDetail {
  return {
    id: 'own-rt', stream, title: 'Item', organisation: '', fit: null, deadline: null, state: 'unseen', provisional: false, ...rowDates,
    detail: { reasons: [], trust: { state: 'unconfirmed', desktop: '', phone: '' }, originalUrl: '', fields, sources: [], documents: [], changes: [], note: null, state: 'unseen', ownItem: { shareConsent: false, published: false } },
  } as unknown as OwnedDetail;
}

test.each([
  ['deadline with a time', stored('tender', { deadline: '2026-12-07' }, [{ name: 'deadlineAt', value: '2026-12-07T17:00:00+02:00' }]), { deadline: '7 Dec 2026, 5pm' }, { deadline: '2026-12-07T17:00' }],
  ['deadline, date only', stored('tender', { deadline: '2026-12-07' }, [{ name: 'deadlineAt', value: '2026-12-07T23:59:59+02:00' }]), { deadline: '7 Dec 2026' }, { deadline: '2026-12-07' }],
  [
    'same-day event with start and end times',
    stored('event', { eventDates: { start: '2026-12-07', end: '2026-12-07' } }, [{ name: 'eventStart', value: '2026-12-07T09:00:00+02:00' }, { name: 'eventEnd', value: '2026-12-07T13:30:00+02:00' }]),
    { eventStart: '7 Dec 2026, 9am', eventEnd: '7 Dec 2026, 1:30pm' },
    { eventStart: '2026-12-07T09:00', eventEnd: '2026-12-07T13:30' },
  ],
  [
    'same-day event, date only end',
    stored('event', { eventDates: { start: '2026-12-07', end: '2026-12-07' } }, [{ name: 'eventStart', value: '2026-12-07T09:00:00+02:00' }, { name: 'eventEnd', value: '2026-12-07T23:59:59+02:00' }]),
    { eventStart: '7 Dec 2026, 9am', eventEnd: '7 Dec 2026' },
    { eventStart: '2026-12-07T09:00', eventEnd: '2026-12-07' },
  ],
  [
    'multi-day event',
    stored('event', { eventDates: { start: '2026-12-01', end: '2026-12-03' } }, [{ name: 'eventStart', value: '2026-12-01T00:00:00+02:00' }, { name: 'eventEnd', value: '2026-12-03T23:59:59+02:00' }]),
    { eventStart: '1 Dec 2026', eventEnd: '3 Dec 2026' },
    { eventStart: '2026-12-01', eventEnd: '2026-12-03' },
  ],
  [
    'event with a start only',
    stored('event', { eventDates: { start: '2026-12-01', end: null } }, [{ name: 'eventStart', value: '2026-12-01T10:00:00+02:00' }]),
    { eventStart: '1 Dec 2026, 10am', eventEnd: '' },
    { eventStart: '2026-12-01T10:00', eventEnd: null },
  ],
  [
    'event dates from the row only (no stored instants)',
    stored('event', { eventDates: { start: '2026-12-07', end: '2026-12-07' } }, []),
    { eventStart: '7 Dec 2026', eventEnd: '7 Dec 2026' },
    { eventStart: '2026-12-07', eventEnd: '2026-12-07' },
  ],
] as const)('date round trip, %s: loads as typed, and an untouched save changes nothing', (_name, item, shown, sent) => {
  const form = toForm(item);
  expect(form).toMatchObject(shown);
  expect(validate(form)).toEqual({});
  expect(toInput(form)).toMatchObject(sent);
  expect(changedInput(form, { ...form })).toEqual({});
});

test('an edit sends only what changed', () => {
  const loaded = toForm(stored('event', { eventDates: { start: '2026-12-07', end: '2026-12-07' } }, [{ name: 'eventStart', value: '2026-12-07T09:00:00+02:00' }, { name: 'eventEnd', value: '2026-12-07T13:30:00+02:00' }, { name: 'organisation', value: 'RDB' }]));
  expect(changedInput(loaded, { ...loaded, title: 'Item 2' })).toEqual({ title: 'Item 2' });
  expect(changedInput(loaded, { ...loaded, organisation: '' })).toEqual({ organisation: null });
  // The same instant typed another way is not a change.
  expect(changedInput(loaded, { ...loaded, eventEnd: '07/12/2026 13:30' })).toEqual({});
  expect(changedInput(loaded, { ...loaded, eventEnd: '7 Dec 2026, 2pm' })).toEqual({ eventEnd: '2026-12-07T14:00' });
  // A value brings its currency; a new stream clears the other stream's dates.
  expect(changedInput(loaded, { ...loaded, value: '5000000' })).toEqual({ value: 5000000, currency: 'RWF' });
  expect(changedInput(loaded, { ...loaded, stream: 'tender', deadline: '9 Dec 2026' })).toEqual({ stream: 'tender', deadline: '2026-12-09', eventStart: null, eventEnd: null });
});
