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
  for (const m of ['FeedContent', 'FeedItem', 'OpportunityOut', 'ProfileOut', 'BusinessData', 'PersonalData', 'DigestSettingsOut', 'UserOut', 'ProfileIn', 'DigestSettingsIn']) {
    expect(schemas[m], m).toBeDefined();
  }
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
  expect(res.detail.fields.some((f) => typeof f.value === 'number')).toBe(true);
});

test('the old stub shapes would fail: documents as strings, a null the API omits', async () => {
  const res = (await call('GET', '/api/opportunities/wfp-logistics')).json as { detail: Record<string, unknown> };
  expect(fits({ ...res, detail: { ...res.detail, documents: ['rfp.pdf'] } }, 'OpportunityOut')).toEqual(['$.detail.documents[0]: expected object, got string']);
  expect(fits({ ...res, topFlag: null }, 'OpportunityOut')).toEqual(['$.topFlag: the API leaves this out when empty, never null']);
  const digest = (await call('GET', '/api/digest-settings')).json as object;
  expect(fits({ ...digest, address: 'x@y.rw' }, 'DigestSettingsOut')).toEqual(["$.address: not in the API's DigestSettingsOut"]);
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

test('GET and PUT /api/digest-settings; PUT refuses an address', async () => {
  const got = await call('GET', '/api/digest-settings');
  expect(fits(got.json, 'DigestSettingsOut')).toEqual([]);
  const body = { channel: 'email', frequency: 'off', day: 'mon', alertThreshold: 60, streams: ['investment'] };
  expect(fits(body, 'DigestSettingsIn')).toEqual([]);
  const put = await call('PUT', '/api/digest-settings', body);
  expect(fits(put.json, 'DigestSettingsOut')).toEqual([]);
  expect((await call('PUT', '/api/digest-settings', { ...body, address: 'x@y.rw' })).status).toBe(422);
});

test('GET /me', async () => {
  expect(fits((await call('GET', '/me')).json, 'UserOut')).toEqual([]);
});
