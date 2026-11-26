// @vitest-environment node
/**
 * The e2e stub's M4 routes (tests/e2e/stubM4.ts, docs/api-contract.md section 5).
 * A manual item's feed row and opportunity answer keep the API's FeedItem and
 * OpportunityOut shapes (the owner-only `detail.ownItem` aside, which the
 * contract has not dumped yet); calendar, feed link, consent, publish and the
 * feed filters behave as the screens expect.
 */
import { afterAll, beforeAll, expect, test } from 'vitest';
import { startStubApi, STUB_COOKIE } from '../e2e/stubApi';
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

async function call(session: string, method: string, path: string, body?: unknown) {
  const res = await fetch(base + path, {
    method,
    headers: { Cookie: `${STUB_COOKIE}=${session}`, ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  return { status: res.status, json: text ? (JSON.parse(text) as Record<string, any>) : undefined };
}

test('calendar: entries by day, kinds, saved only, window cap', async () => {
  const all = await call('m4a', 'GET', '/api/calendar?from=2026-11-01&to=2026-12-31&kind=all');
  expect(all.status).toBe(200);
  const days = all.json!.days as { date: string; entries: { id: string; kind: string; time?: string }[] }[];
  expect(days.map((d) => d.date)).toEqual(['2026-11-30', '2026-12-01', '2026-12-02', '2026-12-07']);
  expect(days[0]!.entries[0]).toMatchObject({ id: 'wfp-logistics', kind: 'deadline', time: '17:00' });
  expect(days[1]!.entries[0]!.kind).toBe('event_start');
  const events = await call('m4a', 'GET', '/api/calendar?from=2026-11-01&to=2026-12-31&kind=events');
  expect((events.json!.days as unknown[]).length).toBe(2);
  await call('m4a', 'PUT', '/api/opportunities/t2s-call/state', { state: 'saved' });
  const saved = await call('m4a', 'GET', '/api/calendar?from=2026-11-01&to=2026-12-31&kind=all&saved=true');
  expect(saved.json!.days).toEqual([{ date: '2026-12-07', entries: [expect.objectContaining({ id: 't2s-call', state: 'saved' })] }]);
  expect((await call('m4a', 'GET', '/api/calendar?from=2026-01-01&to=2026-12-31&kind=all')).status).toBe(422);
});

test('feed link: rotate gives a new one', async () => {
  const a = (await call('m4b', 'GET', '/api/calendar/feed-link')).json!.url;
  const b = (await call('m4b', 'POST', '/api/calendar/feed-link/rotate')).json!.url;
  expect(a).toMatch(/^https:\/\/.+calendar\.ics\?token=/);
  expect(b).not.toBe(a);
  expect((await call('m4b', 'GET', '/api/calendar/feed-link')).json!.url).toBe(b);
});

test('private items: create, shapes, edit, consent, publish, delete', async () => {
  const created = await call('m4c', 'POST', '/api/items', { stream: 'tender', title: 'Fuel supply', organisation: 'Kigali Bus', deadline: '2026-12-10', value: 2000000, currency: 'RWF', url: 'https://example.rw/n' });
  expect(created.status).toBe(201);
  const id = created.json!.id as string;
  const { ownItem, ...detail } = created.json!.detail;
  expect(ownItem).toMatchObject({ shareConsent: false, visibility: 'private', input: { title: 'Fuel supply' } });
  expect(fits({ ...created.json, detail }, 'OpportunityOut')).toEqual([]);
  const feed = await call('m4c', 'GET', '/api/feed');
  const row = (feed.json!.items as { id: string }[]).find((i) => i.id === id);
  expect(fits(row, 'FeedItem')).toEqual([]);

  expect((await call('m4c', 'POST', '/api/items', { stream: 'tender', title: 'x', url: 'javascript:alert(1)' })).status).toBe(422);
  const edited = await call('m4c', 'PATCH', `/api/items/${id}`, { title: 'Fuel supply, phase 2' });
  expect(edited.json!.title).toBe('Fuel supply, phase 2');

  expect((await call('m4c', 'POST', `/api/admin/catalogue/${id}/publish`)).status).toBe(409);
  expect((await call('m4c', 'GET', '/api/admin/catalogue?shareable=true')).json!.items).toEqual([]);
  await call('m4c', 'PUT', `/api/items/${id}/share-consent`, { allow: true });
  expect(((await call('m4c', 'GET', '/api/admin/catalogue?shareable=true')).json!.items as { id: string }[]).map((i) => i.id)).toEqual([id]);
  expect((await call('m4c', 'POST', `/api/admin/catalogue/${id}/publish`)).status).toBe(200);
  const after = await call('m4c', 'GET', `/api/opportunities/${id}`);
  expect(after.json!.detail.ownItem.visibility).toBe('public');
  expect(after.json!.detail.changes[0]).toMatchObject({ field: 'visibility', new: 'public' });

  expect((await call('m4c', 'DELETE', `/api/items/${id}`)).status).toBe(204);
  expect((await call('m4c', 'GET', `/api/opportunities/${id}`)).status).toBe(404);
  expect((await call('m4c', 'PATCH', '/api/items/wfp-logistics', { title: 'x' })).status).toBe(404);
});

test('feed filters narrow the feed', async () => {
  const ids = async (q: string) => ((await call('m4d', 'GET', `/api/feed${q}`)).json!.items as { id: string }[]).map((i) => i.id).sort();
  expect(await ids('?fit=good')).toEqual(['wfp-logistics']);
  expect(await ids('?fit=possible')).toEqual(['t2s-call', 'wfp-logistics']);
  expect(await ids('?window=7')).toEqual(['abh-summit', 'wfp-logistics']);
  expect(await ids('?verification=unconfirmed')).toEqual(['wfp-logistics']);
  expect(await ids('?profile=p3')).toEqual(['abh-summit', 'tbond-5y']);
  expect(await ids('?source=src-rse')).toEqual(['tbond-5y']);
  expect((await call('m4d', 'GET', '/api/feed?fit=7')).status).toBe(422);
});
