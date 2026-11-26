import { expect, test } from 'vitest';
import type { BenchmarkCategory } from '../api/m5';
import {
  categoryFallbackLabel,
  categorySentence,
  currencyWord,
  detailBenchmarkSentence,
  fullAmount,
  methodWords,
  periodFrom,
  plannedWhen,
  shortAmount,
} from './benchmarkWords';

const cat = (over: Partial<BenchmarkCategory> = {}): BenchmarkCategory => ({
  category: 'road-works',
  label: 'Road works',
  awards: 14,
  median: 6_100_000,
  p25: 4_200_000,
  p75: 9_800_000,
  min: 1_000_000,
  max: 20_000_000,
  currency: 'RWF',
  medianBidders: 5,
  ...over,
});

test('amounts: millions and billions abbreviated, smaller amounts in full, RWF written FRW', () => {
  expect(shortAmount(4_200_000, 'RWF')).toBe('FRW 4.2M');
  expect(shortAmount(6_000_000, 'RWF')).toBe('FRW 6M');
  expect(shortAmount(1_500_000_000, 'RWF')).toBe('FRW 1.5B');
  expect(shortAmount(999_999_999, 'RWF')).toBe('FRW 1B');
  expect(shortAmount(850_000, 'RWF')).toBe('FRW 850,000');
  expect(shortAmount(48_500, 'USD')).toBe('USD 48,500');
  expect(shortAmount(1_250_000, 'usd')).toBe('USD 1.3M');
  expect(shortAmount(5, null)).toBe('FRW 5');
  expect(currencyWord('EUR')).toBe('EUR');
  expect(fullAmount('6120000.00', 'RWF')).toBe('FRW 6,120,000');
  expect(fullAmount(1250.5, 'USD')).toBe('USD 1,250.50');
  expect(fullAmount(null, 'RWF')).toBeNull();
  expect(fullAmount('n/a', 'RWF')).toBeNull();
});

test('a category in plain words, with the middle award and the usual number of bidders', () => {
  expect(categorySentence(cat())).toBe('Most awards were between FRW 4.2M and FRW 9.8M; the middle one was FRW 6.1M (14 awards). Usually 5 bidders.');
  expect(categorySentence(cat({ medianBidders: null }))).toBe('Most awards were between FRW 4.2M and FRW 9.8M; the middle one was FRW 6.1M (14 awards).');
  expect(categorySentence(cat({ medianBidders: 1, awards: 3 }))).toContain('(3 awards). Usually 1 bidder.');
  expect(categorySentence(cat({ medianBidders: 4.5 }))).toContain('Usually 5 bidders.');
  // Amounts as strings (decimal) read the same.
  expect(categorySentence(cat({ p25: '4200000.00', p75: '9800000.00', median: '6100000.00' }))).toContain('between FRW 4.2M and FRW 9.8M; the middle one was FRW 6.1M');
  // Both ends the same once rounded.
  expect(categorySentence(cat({ p25: 4_210_000, p75: 4_240_000 }))).toContain('Most awards were about FRW 4.2M;');
  expect(categorySentence(cat({ currency: 'USD', p25: 40_000, p75: 90_000, median: 61_000 }))).toBe(
    'Most awards were between USD 40,000 and USD 90,000; the middle one was USD 61,000 (14 awards). Usually 5 bidders.',
  );
});

test('fewer than 3 awards: counts only, no range', () => {
  const few = cat({ awards: 2, median: null, p25: null, p75: null, min: null, max: null, medianBidders: null });
  expect(categorySentence(few)).toBe('Only 2 awards so far — not enough to show a range.');
  expect(categorySentence({ ...few, awards: 1 })).toBe('Only 1 award so far — not enough to show a range.');
  expect(categorySentence({ ...few, awards: 0 })).toBe('No awards in this period yet.');
  // Even if numbers came with 2 awards, no range is shown.
  expect(categorySentence(cat({ awards: 2 }))).toBe('Only 2 awards so far — not enough to show a range.');
});

test('the tender detail line', () => {
  expect(detailBenchmarkSentence({ category: 'road-works', median: 6_100_000, p25: 4_200_000, p75: 9_800_000, awards: 14, currency: 'RWF' })).toBe(
    'Similar contracts were usually awarded between FRW 4.2M and FRW 9.8M (14 awards).',
  );
  expect(detailBenchmarkSentence({ category: 'x', median: 1, p25: null, p75: 2, awards: 14, currency: 'RWF' })).toBeNull();
  expect(detailBenchmarkSentence({ category: 'x', median: 1, p25: 1, p75: 2, awards: 2, currency: 'RWF' })).toBeNull();
  expect(detailBenchmarkSentence(undefined)).toBeNull();
});

test('periods end today (Kigali) and start 12 months or 2 years back; all has no start', () => {
  expect(periodFrom('12m', '2026-11-24')).toBe('2025-11-24');
  expect(periodFrom('2y', '2026-11-24')).toBe('2024-11-24');
  expect(periodFrom('12m', '2028-02-29')).toBe('2027-03-01');
  expect(periodFrom('all', '2026-11-24')).toBeUndefined();
});

test('planned dates, methods and category labels in words', () => {
  // The API's label first: it says fiscal or calendar correctly.
  expect(plannedWhen('2027-Q1', 'January to March 2027')).toBe('January to March 2027');
  expect(plannedWhen('2026-10-01/2027-03-31', 'October 2026 to March 2027')).toBe('October 2026 to March 2027');
  expect(plannedWhen('2027-Q1', '  ')).toBe('January to March 2027');
  // Quarters as month ranges, dates with the day, ranges in words; never raw ISO.
  expect(plannedWhen('2027-Q1')).toBe('January to March 2027');
  expect(plannedWhen('Q3 2027')).toBe('July to September 2027');
  expect(plannedWhen('2027-03')).toBe('March 2027');
  expect(plannedWhen('2027-02-17')).toBe('17 Feb 2027');
  expect(plannedWhen('2026-09-17')).toBe('17 Sep 2026');
  expect(plannedWhen('2027-03-15/2027-06-30')).toBe('15 Mar 2027 to 30 Jun 2027');
  expect(plannedWhen('2027-01-01/2027-06-30')).toBe('January to June 2027');
  expect(plannedWhen('2026-10-01/2027-03-31')).toBe('October 2026 to March 2027');
  expect(plannedWhen('2027-02-17/2027-02-17')).toBe('17 Feb 2027');
  expect(plannedWhen('2027-02-30')).toBeNull();
  expect(plannedWhen('2027-13')).toBeNull();
  expect(plannedWhen('2027-01-01/soon')).toBeNull();
  expect(plannedWhen('second half of FY 2026/27')).toBe('second half of FY 2026/27');
  expect(plannedWhen(null)).toBeNull();
  expect(methodWords('open_competitive_bidding')).toBe('Open competitive bidding');
  expect(methodWords('')).toBeNull();
  expect(categoryFallbackLabel('road-works')).toBe('Road works');
});
