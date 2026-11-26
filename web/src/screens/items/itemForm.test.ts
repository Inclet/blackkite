import { afterEach, beforeEach, expect, test } from 'vitest';
import { setNowForTests } from '../../lib/now';
import { emptyForm, ITEM_ERRORS, serverErrors, toForm, toInput, validate } from './itemForm';
import type { OwnedDetail } from '../../api/m4';

beforeEach(() => setNowForTests('2026-11-24T14:00:00+02:00'));
afterEach(() => setNowForTests(null));

const base = { ...emptyForm(), stream: 'tender' as const, title: 'Fuel supply' };

test('stream and title are needed; everything else may stay empty', () => {
  expect(validate(emptyForm())).toEqual({ stream: ITEM_ERRORS.stream, title: ITEM_ERRORS.title });
  expect(validate(base)).toEqual({});
});

test('dates need a real day with a year, in a plausible window', () => {
  expect(validate({ ...base, deadline: '2026-12-07' })).toEqual({});
  expect(validate({ ...base, deadline: '7 Dec' }).deadline).toBe(ITEM_ERRORS.date);
  expect(validate({ ...base, deadline: '2026-02-30' }).deadline).toBe(ITEM_ERRORS.date);
  // The API's window: a year back, two years ahead (today 24 Nov 2026).
  expect(validate({ ...base, deadline: '2025-11-23' }).deadline).toBe(ITEM_ERRORS.dateRange);
  expect(validate({ ...base, deadline: '2025-11-24' })).toEqual({});
  expect(validate({ ...base, deadline: '2028-11-24' })).toEqual({});
  expect(validate({ ...base, deadline: '2028-11-25' }).deadline).toBe(ITEM_ERRORS.dateRange);
});

test('events: an end needs a start, and not before it', () => {
  const ev = { ...base, stream: 'event' as const };
  expect(validate({ ...ev, eventEnd: '2026-12-02' }).eventStart).toBe(ITEM_ERRORS.eventStart);
  expect(validate({ ...ev, eventStart: '2026-12-03', eventEnd: '2026-12-02' }).eventEnd).toBe(ITEM_ERRORS.eventEnd);
  expect(validate({ ...ev, eventStart: '2026-12-01', eventEnd: '2026-12-02' })).toEqual({});
});

test('value is a whole number; links are http(s) only', () => {
  expect(validate({ ...base, value: '5,000,000' })).toEqual({});
  expect(validate({ ...base, value: '5m' }).value).toBe(ITEM_ERRORS.value);
  expect(validate({ ...base, url: 'javascript:alert(1)' }).url).toBe(ITEM_ERRORS.url);
  expect(validate({ ...base, url: 'ftp://x.rw/a' }).url).toBe(ITEM_ERRORS.url);
  expect(validate({ ...base, url: 'https://example.rw/notice' })).toEqual({});
});

test('the body: empty fields null, deadline or event dates by stream, currency only with a value', () => {
  expect(toInput({ ...base, deadline: '2026-12-07', eventStart: '2026-12-01', value: '5,000,000', currency: 'USD', notes: '  call Tuesday ' })).toEqual({
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
  const ev = toInput({ ...base, stream: 'event', deadline: '2026-12-07', eventStart: '2026-12-01' });
  expect([ev.deadline, ev.eventStart, ev.currency]).toEqual([null, '2026-12-01', null]);
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
    eventStart: '2026-12-01',
    eventEnd: '2026-12-02',
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
