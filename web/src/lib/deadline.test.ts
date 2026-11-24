import { afterEach, beforeEach, expect, test } from 'vitest';
import { setNowForTests } from './now';
import { daysLeft, deadlineLabel, deadlineWeight, eventLabel, eventWeight, kigaliToday } from './deadline';

beforeEach(() => setNowForTests('2026-11-24T14:00:00+02:00'));
afterEach(() => setNowForTests(null));

test('today is taken in Kigali', () => {
  setNowForTests('2026-11-24T23:30:00Z'); // 01:30 on the 25th in Kigali
  expect(kigaliToday()).toBe('2026-11-25');
});

test.each([
  ['2026-12-26', 32, 'quiet', '32 days left'],
  ['2026-12-09', 15, 'quiet', '15 days left'],
  ['2026-12-08', 14, 'outlined', '14 days left'],
  ['2026-12-06', 12, 'outlined', '12 days left'],
  ['2026-12-01', 7, 'solid', '7 days left'],
  ['2026-11-30', 6, 'solid', '6 days left'],
  ['2026-11-25', 1, 'alert', 'Closes tomorrow'],
  ['2026-11-24', 0, 'alert', 'Closes today'],
] as const)('%s: %i days, %s, "%s"', (date, days, weight, label) => {
  expect(daysLeft(date)).toBe(days);
  expect(deadlineWeight(days)).toBe(weight);
  expect(deadlineLabel(date)).toBe(label);
});

test('closed deadlines read as a short date', () => {
  expect(deadlineLabel('2026-11-23')).toBe('Closed 23 Nov');
});

test.each([
  [15, 'quiet'],
  [14, 'outlined'],
  [7, 'outlined'],
  [6, 'solid'],
  [2, 'solid'],
  [1, 'alert'],
  [0, 'alert'],
  [-1, 'alert'],
] as const)('event %i days from its start: %s (decision 23)', (days, weight) => {
  expect(eventWeight(days)).toBe(weight);
});

test('event labels', () => {
  expect(eventLabel('2026-12-01', '2026-12-02')).toBe('1 to 2 Dec');
  expect(eventLabel('2026-12-01')).toBe('1 Dec');
  expect(eventLabel('2026-11-30', '2026-12-02')).toBe('30 Nov to 2 Dec');
});
