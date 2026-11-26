// @vitest-environment node
/**
 * The e2e stub (tests/e2e/stubApi.ts) answers in the member API's real shapes.
 * api-schemas.json is dumped from the API's Pydantic models (see README.md
 * here); nothing is imported from api/.
 */
import { afterAll, beforeAll, describe, expect, test } from 'vitest';
import { defaultItems, startStubApi, STUB_COOKIE } from '../e2e/stubApi';
import dump from './api-schemas.json' with { type: 'json' };
import { check, type Schema } from './schemaCheck';

const schemas = dump.schemas as unknown as Record<string, Schema>;
// The codes StateIn accepts, read from the dump (src/api/types.ts DISMISS_REASONS must equal these:
// src/api/requestContract.test.ts checks it).
const DISMISS_REASON_CODES = (schemas.StateIn?.properties?.dismissReason?.anyOf?.find((s) => s.type === 'string')?.enum ?? []) as string[];
const opts = { omitIfNone: dump.omitIfNone as Record<string, string[]> };
const fits = (value: unknown, model: string) => check(value, schemas[model]!, opts);

let base = '';
let close: () => Promise<void>;
beforeAll(async () => {
  const stub = await startStubApi(0);
  base = `http://127.0.0.1:${stub.port}`;
  close = stub.close;
});
afterAll(() => close());

async function call(method: string, path: string, body?: unknown): Promise<{ status: number; json: unknown }> {
  const res = await fetch(base + path, {
    method,
    headers: { Cookie: `${STUB_COOKIE}=contract`, ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  return { status: res.status, json: text ? JSON.parse(text) : undefined };
}

describe('the checker', () => {
  const s: Schema = {
    title: 'M',
    type: 'object',
    properties: { a: { type: 'integer' }, b: { anyOf: [{ type: 'string' }, { type: 'null' }] }, d: { type: 'string', format: 'date-time' } },
    required: ['a'],
  };
  test('passes a fitting value and names each problem', () => {
    expect(check({ a: 1, b: null, d: '2026-11-24T08:00:00Z' }, s)).toEqual([]);
    expect(check({ b: 2, c: 1, d: '24 Nov' }, s)).toEqual([
      '$.a: missing (always sent by the API)',
      '$.b: expected string | null, got integer',
      '$.c: not in the API\'s M',
      '$.d: "24 Nov" is not an ISO date-time',
    ]);
    expect(check({ a: 1.5 }, s)).toEqual(['$.a: expected integer, got number']);
    expect(check({ a: 1, b: null }, s, { omitIfNone: { M: ['b'] } })).toEqual(['$.b: the API leaves this out when empty, never null']);
  });
});

test('the schema file has every model the web app reads or sends', () => {
  for (const m of ['FeedContent', 'FeedItem', 'OpportunityOut', 'ProfileOut', 'BusinessData', 'PersonalData', 'DigestSettingsOut', 'UserOut', 'ProfileIn', 'DigestSettingsIn', 'StateIn']) {
    expect(schemas[m], m).toBeDefined();
  }
});

test('the dumped contract has the Phase 4 shapes: alertMinFit, provisional, StateIn with the reason codes', () => {
  const digestIn = Object.keys(schemas.DigestSettingsIn!.properties!);
  expect(digestIn).toContain('alertMinFit');
  expect(digestIn).not.toContain('alertThreshold');
  expect(Object.keys(schemas.DigestSettingsOut!.properties!)).not.toContain('alertThreshold');
  expect(schemas.FeedItem!.required).toContain('provisional');
  expect(schemas.FeedContent!.$defs!.FeedItem!.required).toContain('provisional');
  expect(schemas.OpportunityOut!.required).toContain('provisional');
  expect(schemas.StateIn).toBeDefined();
  expect(DISMISS_REASON_CODES).toHaveLength(5);
});

test('GET /api/feed and /api/shortlist', async () => {
  const feed = await call('GET', '/api/feed');
  expect(feed.status).toBe(200);
  expect(fits(feed.json, 'FeedContent')).toEqual([]);
  expect((feed.json as { items: unknown[] }).items).toHaveLength(defaultItems().length);

  await call('PUT', '/api/opportunities/wfp-logistics/state', { state: 'saved' });
  const shortlist = await call('GET', '/api/shortlist');
  expect(shortlist.json).toHaveLength(1);
  for (const item of shortlist.json as unknown[]) expect(fits(item, 'FeedItem')).toEqual([]);
});

test.each(defaultItems().map((i) => i.id))('GET /api/opportunities/%s', async (id) => {
  const res = await call('GET', `/api/opportunities/${id}`);
  expect(res.status).toBe(200);
  expect(fits(res.json, 'OpportunityOut')).toEqual([]);
});

test('the detail stub carries the shapes the screens must handle: documents by name, list values with snippets', async () => {
  const res = (await call('GET', '/api/opportunities/wfp-logistics')).json as { detail: { documents: unknown[]; fields: { value: unknown; snippets?: unknown }[] } };
  expect(res.detail.documents[0]).toEqual({ name: expect.any(String) });
  expect(res.detail.fields.some((f) => Array.isArray(f.value) && Array.isArray(f.snippets))).toBe(true);
  // Amounts: the decimal as a string, with the API's wording in display (valueAmount only).
  expect(res.detail.fields.find((f) => (f as { name?: string }).name === 'valueAmount')).toMatchObject({ value: '120000000.00', display: 'FRW 120,000,000' });
  expect(res.detail.fields.filter((f) => 'display' in f)).toHaveLength(1);
  expect((res.detail as unknown as { isManual: unknown }).isManual).toBe(false);
});

test('every feed item says whether its profile is provisional', async () => {
  const feed = (await call('GET', '/api/feed')).json as { items: Record<string, unknown>[]; user: { name: string } };
  for (const i of feed.items) expect(typeof i.provisional).toBe('boolean');
  expect(feed.items.find((i) => i.id === 't2s-call')!.provisional).toBe(true);
  const { provisional: _p, ...without } = feed.items[0]!;
  expect(fits(without, 'FeedItem')).toEqual(['$.provisional: missing (always sent by the API)']);
});

test('PUT state: the five dismiss reason codes, nothing else', async () => {
  for (const code of DISMISS_REASON_CODES) {
    const body = { state: 'dismissed', dismissReason: code };
    expect(fits(body, 'StateIn')).toEqual([]);
    expect((await call('PUT', '/api/opportunities/abh-summit/state', body)).status).toBe(200);
  }
  expect(fits({ state: 'dismissed', dismissReason: 'Too far' }, 'StateIn')).toHaveLength(1);
  expect((await call('PUT', '/api/opportunities/abh-summit/state', { state: 'dismissed', dismissReason: 'Too far' })).status).toBe(422);
  expect((await call('PUT', '/api/opportunities/abh-summit/state', { state: 'unseen' })).status).toBe(200);
});

test('the old stub shapes would fail: documents as strings, a null the API omits', async () => {
  const res = (await call('GET', '/api/opportunities/wfp-logistics')).json as { detail: Record<string, unknown> };
  expect(fits({ ...res, detail: { ...res.detail, documents: ['rfp.pdf'] } }, 'OpportunityOut')).toEqual(['$.detail.documents[0]: expected object, got string']);
  expect(fits({ ...res, topFlag: null }, 'OpportunityOut')).toEqual(['$.topFlag: the API leaves this out when empty, never null']);
  const digest = (await call('GET', '/api/digest-settings')).json as object;
  expect(fits({ ...digest, address: 'x@y.rw' }, 'DigestSettingsOut')).toEqual(["$.address: not in the API's DigestSettingsOut"]);
  const { alertMinFit: _a, ...rest } = digest as Record<string, unknown>;
  expect(fits({ ...rest, alertThreshold: 70 }, 'DigestSettingsOut')).toEqual([
    '$.alertMinFit: missing (always sent by the API)',
    "$.alertThreshold: not in the API's DigestSettingsOut",
  ]);
});

test('GET /api/profiles: each profile, and its data against its type\'s model', async () => {
  const res = await call('GET', '/api/profiles');
  const list = res.json as { type: string; data: unknown }[];
  expect(list.length).toBeGreaterThan(0);
  for (const p of list) {
    expect(fits(p, 'ProfileOut')).toEqual([]);
    expect(fits(p.data, p.type === 'business' ? 'BusinessData' : 'PersonalData')).toEqual([]);
  }
});

test('POST and PATCH /api/profiles answer a ProfileOut; the stub refuses what the API refuses', async () => {
  const body = { name: 'AI lab', type: 'business', active: true, data: { streams: ['tender'], services: ['AI/ML'], provisional: true } };
  expect(fits(body, 'ProfileIn')).toEqual([]);
  const created = await call('POST', '/api/profiles', body);
  expect(created.status).toBe(201);
  expect(fits(created.json, 'ProfileOut')).toEqual([]);

  const id = (created.json as { id: string }).id;
  const patched = await call('PATCH', `/api/profiles/${id}`, { data: { streams: ['tender', 'event'] } });
  expect(fits(patched.json, 'ProfileOut')).toEqual([]);

  expect((await call('PATCH', `/api/profiles/${id}`, { type: 'personal', data: { streams: ['event'], services: ['AI/ML'] } })).status).toBe(422);
  expect((await call('POST', '/api/profiles', { ...body, data: { streams: [] } })).status).toBe(422);
});

test('GET and PUT /api/digest-settings; PUT refuses an address and a numeric threshold', async () => {
  const got = await call('GET', '/api/digest-settings');
  expect(fits(got.json, 'DigestSettingsOut')).toEqual([]);
  const body = { channel: 'email', frequency: 'off', day: 'mon', alertMinFit: 'good', streams: ['investment'] };
  expect(fits(body, 'DigestSettingsIn')).toEqual([]);
  const put = await call('PUT', '/api/digest-settings', body);
  expect(fits(put.json, 'DigestSettingsOut')).toEqual([]);
  expect((await call('PUT', '/api/digest-settings', { ...body, address: 'x@y.rw' })).status).toBe(422);
  expect((await call('PUT', '/api/digest-settings', { ...body, alertMinFit: 60 })).status).toBe(422);
  expect(fits({ ...body, alertMinFit: 'possible' }, 'DigestSettingsIn')).toHaveLength(1);
  expect((await call('PUT', '/api/digest-settings', { ...body, alertMinFit: null })).status).toBe(200);
});

test('GET /me', async () => {
  expect(fits((await call('GET', '/me')).json, 'UserOut')).toEqual([]);
});

test('no name: the feed sends "" and GET /me sends null', async () => {
  const res = await fetch(`${base}/__stub/sessions/noname`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ userName: '' }) });
  expect(res.status).toBe(204);
  const get = async (path: string) => (await fetch(base + path, { headers: { Cookie: `${STUB_COOKIE}=noname` } })).json();
  const feed = (await get('/api/feed')) as { user: { name: string } };
  expect(feed.user.name).toBe('');
  expect(fits(feed, 'FeedContent')).toEqual([]);
  const me = (await get('/me')) as { name: unknown };
  expect(me.name).toBeNull();
  expect(fits(me, 'UserOut')).toEqual([]);
});
