import { afterEach, expect, test } from 'vitest';
import { addDays, currentMonth, dayTitle, formatTime, monthRange, monthTitle, monthWeeks, parseMonth, shiftMonth } from './calendar';
import { setNowForTests } from './now';

afterEach(() => setNowForTests(null));

test('this month in Kigali, and ?month= when well formed', () => {
  setNowForTests('2026-11-30T23:30:00Z'); // 1 Dec, 01:30 in Kigali
  expect(currentMonth()).toBe('2026-12');
  expect(parseMonth('2027-02')).toBe('2027-02');
  expect(parseMonth('2027-13')).toBe('2026-12');
  expect(parseMonth(null)).toBe('2026-12');
});

test('month arithmetic, ranges and titles', () => {
  expect(shiftMonth('2026-12', 1)).toBe('2027-01');
  expect(shiftMonth('2026-01', -1)).toBe('2025-12');
  expect(monthRange('2028-02')).toEqual({ from: '2028-02-01', to: '2028-02-29' });
  expect(monthTitle('2026-11')).toBe('November 2026');
  expect(dayTitle('2026-11-24')).toBe('Tuesday 24 November 2026');
  expect(addDays('2026-11-30', 1)).toBe('2026-12-01');
});

test('weeks start on Monday; cells outside the month are empty', () => {
  const weeks = monthWeeks('2026-11'); // 1 Nov 2026 is a Sunday
  expect(weeks[0]).toEqual([null, null, null, null, null, null, '2026-11-01']);
  expect(weeks.at(-1)).toEqual(['2026-11-30', null, null, null, null, null, null]);
  expect(weeks).toHaveLength(6);
});

test('times in the boards\' voice', () => {
  expect(formatTime('17:00')).toBe('5pm');
  expect(formatTime('09:30')).toBe('9:30am');
  expect(formatTime('00:00')).toBe('12am');
  expect(formatTime('12:15')).toBe('12:15pm');
});
