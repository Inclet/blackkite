import { afterEach, beforeEach, expect, test } from 'vitest';
import { setNowForTests } from '../../lib/now';
import { emptyForm, ITEM_ERRORS, toForm, toInput, validate } from './itemForm';

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
  expect(validate({ ...base, deadline: '1999-12-07' }).deadline).toBe(ITEM_ERRORS.dateRange);
  expect(validate({ ...base, deadline: '2037-01-01' }).deadline).toBe(ITEM_ERRORS.dateRange);
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
  expect(toForm(toInput({ ...base, value: '12' }))).toEqual({ ...base, value: '12' });
});
