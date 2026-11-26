// @vitest-environment node
/**
 * The e2e stub's M5 routes (tests/e2e/stubM5.ts, docs/api-contract.md section 6)
 * answer with the keys the contract lists. api-schemas.json has no M5 models yet
 * (the API is built in parallel), so the keys are checked against the contract's
 * text here; once the dump has them, check with schemaCheck as stub.m4.test.ts does.
 */
import { afterAll, beforeAll, expect, test } from 'vitest';
import { startStubApi, STUB_COOKIE } from '../e2e/stubApi';
import { ITEM_CATEGORIES } from '../e2e/stubM5';

let base = '';
let close: () => Promise<void>;
beforeAll(async () => {
  const stub = await startStubApi(0);
  base = `http://127.0.0.1:${stub.port}`;
  close = stub.close;
});
afterAll(() => close());

async function call(session: string, method: string, path: string, body?: unknown) {
  const res = await fetch(base + path, {
    method,
    headers: { Cookie: `${STUB_COOKIE}=${session}`, ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  return { status: res.status, json: text ? (JSON.parse(text) as Record<string, any>) : undefined };
}

const keys = (o: object) => Object.keys(o).sort();

test('GET /api/benchmarks: the contract keys; statistics only from 3 awards; one currency per entry; window and entity filter', async () => {
  const all = await call('m5a', 'GET', '/api/benchmarks');
  expect(all.status).toBe(200);
  const cats = all.json!.categories as Record<string, unknown>[];
  for (const c of cats) expect(keys(c)).toEqual(['awards', 'category', 'currency', 'label', 'max', 'median', 'medianBidders', 'min', 'p25', 'p75']);
  const road = cats.find((c) => c.category === 'road-works')!;
  expect(road).toMatchObject({ awards: 2, median: null, p25: null, p75: null, min: null, max: null, medianBidders: null });
  expect(cats.filter((c) => c.category === 'it-services').map((c) => c.currency).sort()).toEqual(['RWF', 'USD']);
  const year = await call('m5a', 'GET', '/api/benchmarks?from=2025-11-24&to=2026-11-24');
  expect((year.json!.categories as { category: string; awards: number }[]).find((c) => c.category === 'freight')!.awards).toBe(12);
  const kigali = await call('m5a', 'GET', '/api/benchmarks?entity=kigali');
  expect((kigali.json!.categories as { category: string; awards: number }[]).find((c) => c.category === 'road-works')!.awards).toBe(1);
  expect((await call('m5a', 'GET', '/api/benchmarks?from=24 Nov')).status).toBe(422);
});

test('GET /api/benchmarks/{category}: the contract keys, newest first, paged', async () => {
  const first = await call('m5b', 'GET', '/api/benchmarks/freight?limit=20');
  const awards = first.json!.awards as Record<string, unknown>[];
  expect(awards).toHaveLength(20);
  expect(first.json!.total).toBe(23);
  for (const a of awards) {
    expect(keys(a)).toEqual(expect.arrayContaining(['awardedOn', 'bidders', 'entity', 'id', 'tenderRef', 'title', 'url', 'winner', 'winningPrice']));
    for (const b of a.bidders as object[]) expect(keys(b)).toEqual(['name', 'price']);
  }
  const dates = awards.map((a) => a.awardedOn as string);
  expect([...dates].sort().reverse()).toEqual(dates);
  const second = await call('m5b', 'GET', '/api/benchmarks/freight?limit=20&offset=20');
  expect(second.json!.awards).toHaveLength(3);
});

test('GET /api/plans and detail.benchmark (when seeded)', async () => {
  const plans = await call('m5c', 'GET', '/api/plans');
  for (const p of plans.json!.items as object[]) {
    expect(keys(p)).toEqual(expect.arrayContaining(['description', 'entity', 'id', 'matchedProfile', 'method', 'plannedFor', 'url']));
  }
  const plain = await call('m5c', 'GET', '/api/opportunities/wfp-logistics');
  expect(plain.json!.detail).not.toHaveProperty('benchmark');
  await fetch(`${base}/__stub/sessions/m5d`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ itemCategories: ITEM_CATEGORIES }) });
  const seeded = await call('m5d', 'GET', '/api/opportunities/wfp-logistics');
  expect(keys(seeded.json!.detail.benchmark)).toEqual(['awards', 'category', 'currency', 'median', 'p25', 'p75']);
  expect(seeded.json!.detail.benchmark).toMatchObject({ category: 'freight', awards: 23, currency: 'RWF' });
  // Never on other streams.
  const funding = await call('m5d', 'GET', '/api/opportunities/t2s-call');
  expect(funding.json!.detail).not.toHaveProperty('benchmark');
});
