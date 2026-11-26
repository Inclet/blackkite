import { expect, test } from 'vitest';
import { checkItemDate, itemDateText, parseItemDate } from './itemDates';

const NOW = new Date('2026-11-24T14:00:00+02:00');
const value = (text: string, edge: 'start' | 'end' = 'end') => {
  const d = checkItemDate(text, edge, NOW);
  return 'problem' in d ? d.problem : d.value;
};

test('the forms the API reads, with the year, day first', () => {
  expect(value('7 Dec 2026')).toBe('2026-12-07');
  expect(value('7 December 2026')).toBe('2026-12-07');
  expect(value('7th of Dec. 2026')).toBe('2026-12-07');
  expect(value('December 7, 2026')).toBe('2026-12-07');
  expect(value('07/12/2026')).toBe('2026-12-07');
  expect(value('7.12.2026')).toBe('2026-12-07');
  expect(value('07-12-26')).toBe('2026-12-07');
  expect(value('2026-12-07')).toBe('2026-12-07');
});

test('an optional time, Kigali', () => {
  expect(value('7 Dec 2026, 5pm')).toBe('2026-12-07T17:00');
  expect(value('7 Dec 2026 17:00')).toBe('2026-12-07T17:00');
  expect(value('07/12/2026 5:30 p.m.')).toBe('2026-12-07T17:30');
  expect(value('7 Dec 2026 noon')).toBe('2026-12-07T12:00');
  expect(value('12am 7 Dec 2026')).toBe('2026-12-07T00:00');
  expect(value('2026-12-07T17:00')).toBe('2026-12-07T17:00');
  expect(value('2026-12-07T15:00Z')).toBe('2026-12-07T17:00');
  // An impossible time is ignored, as by the API: the date alone.
  expect(value('7 Dec 2026 25:00')).toBe('2026-12-07');
});

test('never a guessed year; nonsense and impossible days are refused', () => {
  expect(value('7 Dec')).toBe('no_year');
  expect(value('Dec 7')).toBe('no_year');
  expect(value('next Friday')).toBe('unparsed');
  expect(value('30 Feb 2026')).toBe('unparsed');
  expect(value('2026-02-30')).toBe('unparsed');
  expect(value('31/04/2026')).toBe('unparsed');
});

test('the plausible window: a year back to two years ahead, as instants', () => {
  // A deadline typed alone is the end of its day; an event start, the start.
  expect(value('24 Nov 2025')).toBe('2025-11-24');
  expect(value('23 Nov 2025')).toBe('out_of_window');
  expect(value('24 Nov 2025', 'start')).toBe('out_of_window');
  // Two years ahead is 730 days: 23 Nov 2028, 2pm (2028 is a leap year).
  expect(value('22 Nov 2028')).toBe('2028-11-22');
  expect(value('23 Nov 2028, 1pm')).toBe('2028-11-23T13:00');
  expect(value('23 Nov 2028')).toBe('out_of_window');
  expect(value('24 Nov 2028', 'start')).toBe('out_of_window');
});

test('instants: the day edge for a date alone', () => {
  const end = parseItemDate('7 Dec 2026', 'end');
  const start = parseItemDate('7 Dec 2026', 'start');
  expect('at' in end && end.at.toISOString()).toBe('2026-12-07T21:59:59.000Z');
  expect('at' in start && start.at.toISOString()).toBe('2026-12-06T22:00:00.000Z');
});

test('stored dates read back as the form shows them', () => {
  expect(itemDateText('2026-12-07', 'end')).toBe('7 Dec 2026');
  expect(itemDateText('2026-12-07T23:59:59+02:00', 'end')).toBe('7 Dec 2026');
  expect(itemDateText('2026-12-07T00:00:00+02:00', 'start')).toBe('7 Dec 2026');
  expect(itemDateText('2026-12-07T15:00:00Z', 'end')).toBe('7 Dec 2026, 5pm');
  expect(itemDateText('2026-12-07T17:30:00+02:00', 'start')).toBe('7 Dec 2026, 5:30pm');
  // Read back, it parses to the same value.
  expect(value(itemDateText('2026-12-07T15:00:00Z', 'end'))).toBe('2026-12-07T17:00');
});
