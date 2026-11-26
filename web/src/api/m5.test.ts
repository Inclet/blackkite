import { afterEach, expect, test, vi } from 'vitest';
import { mockApi } from '../test/mockApi';
import { amountOf, AWARDS_PAGE, m5Api } from './m5';

afterEach(() => vi.unstubAllGlobals());

const url = (api: ReturnType<typeof mockApi>, i = 0) => api.fetch.mock.calls[i]![0] as string;

test('benchmarks: window and entity in the query, nothing empty sent', async () => {
  const api = mockApi({ 'GET /api/benchmarks': { categories: [] } });
  await m5Api.benchmarks({ from: '2025-11-24', to: '2026-11-24', entity: '  RTDA ' });
  expect(url(api)).toBe('/api/benchmarks?from=2025-11-24&to=2026-11-24&entity=RTDA');
  await m5Api.benchmarks({ entity: '  ' });
  expect(url(api, 1)).toBe('/api/benchmarks');
});

test('awards: the category is encoded and paged by limit and offset', async () => {
  const api = mockApi({ 'GET /api/benchmarks/road%20works': { awards: [] } });
  await m5Api.awards('road works', 1);
  expect(url(api)).toBe(`/api/benchmarks/road%20works?limit=${AWARDS_PAGE}`);
  await m5Api.awards('road works', 3);
  expect(url(api, 1)).toBe(`/api/benchmarks/road%20works?limit=${AWARDS_PAGE}&offset=${2 * AWARDS_PAGE}`);
});

test('plans and amounts', async () => {
  const api = mockApi({ 'GET /api/plans': { items: [] } });
  await expect(m5Api.plans()).resolves.toEqual({ items: [] });
  expect(url(api)).toBe('/api/plans');
  expect(amountOf('6000000.00')).toBe(6_000_000);
  expect(amountOf(12)).toBe(12);
  expect(amountOf('')).toBeNull();
  expect(amountOf(null)).toBeNull();
  expect(amountOf('abc')).toBeNull();
});
