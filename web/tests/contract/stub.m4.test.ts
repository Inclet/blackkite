// @vitest-environment node
/**
 * The e2e stub's M4 routes (tests/e2e/stubM4.ts, docs/api-contract.md section 5)
 * answer in the API's built shapes (CalendarOut, FeedLinkOut, OpportunityOut with
 * ownItem, ShareConsentOut, CatalogueItem, RefusalOut), and what the screens send
 * fits ItemIn, ItemPatch and ShareConsentIn.
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
  expect(fits(all.json, 'CalendarOut')).toEqual([]);
  const days = all.json!.days as { date: string; entries: { id: string; kind: string; time?: string }[] }[];
  expect(days.map((d) => d.date)).toEqual(['2026-11-30', '2026-12-01', '2026-12-02', '2026-12-07']);
  expect(days[0]!.entries[0]).toMatchObject({ id: 'wfp-logistics', kind: 'deadline', time: '17:00' });
  expect(days[1]!.entries[0]!.kind).toBe('event_start');
  const events = await call('m4a', 'GET', '/api/calendar?from=2026-11-01&to=2026-12-31&kind=events');
  expect((events.json!.days as unknown[]).length).toBe(2);
  await call('m4a', 'PUT', '/api/opportunities/t2s-call/state', { state: 'saved' });
  const saved = await call('m4a', 'GET', '/api/calendar?from=2026-11-01&to=2026-12-31&kind=all&saved=true');
  expect(saved.json!.days).toEqual([{ date: '2026-12-07', entries: [expect.objectContaining({ id: 't2s-call', state: 'saved' })] }]);
  expect(fits(saved.json, 'CalendarOut')).toEqual([]);
  expect((await call('m4a', 'GET', '/api/calendar?from=2026-01-01&to=2026-12-31&kind=all')).status).toBe(422);
  // At most 120 days inclusive.
  expect((await call('m4a', 'GET', '/api/calendar?from=2026-11-01&to=2027-02-28&kind=all')).status).toBe(200);
  expect((await call('m4a', 'GET', '/api/calendar?from=2026-11-01&to=2027-03-01&kind=all')).status).toBe(422);
});

test('feed link: rotate gives a new one', async () => {
  const first = (await call('m4b', 'GET', '/api/calendar/feed-link')).json!;
  expect(fits(first, 'FeedLinkOut')).toEqual([]);
  expect(first.rotatedAt).toBeNull();
  const rotated = (await call('m4b', 'POST', '/api/calendar/feed-link/rotate')).json!;
  expect(fits(rotated, 'FeedLinkOut')).toEqual([]);
  const [a, b] = [first.url, rotated.url];
  expect(rotated.webcalUrl).toMatch(/^webcal:\/\//);
  expect(a).toMatch(/^https:\/\/.+calendar\.ics\?token=/);
  expect(b).not.toBe(a);
  expect((await call('m4b', 'GET', '/api/calendar/feed-link')).json!.url).toBe(b);
});

test('feed link: 503 when the server has no calendar secret', async () => {
  await fetch(`${base}/__stub/sessions/m4n`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ feedLinkVersion: 0 }) });
  expect((await call('m4n', 'GET', '/api/calendar/feed-link')).status).toBe(503);
});

test('private items: create, shapes, edit, consent, publish, delete', async () => {
  const body = { stream: 'tender', title: 'Fuel supply', organisation: 'Kigali Bus', deadline: '2026-12-10', eventStart: null, eventEnd: null, value: 2000000, currency: 'RWF', location: null, url: 'https://example.rw/n', notes: null };
  expect(fits(body, 'ItemIn')).toEqual([]);
  expect(fits({ title: 'x', organisation: null }, 'ItemPatch')).toEqual([]);
  expect(fits({ allow: true }, 'ShareConsentIn')).toEqual([]);
  const created = await call('m4c', 'POST', '/api/items', body);
  expect(created.status).toBe(201);
  const id = created.json!.id as string;
  expect(created.json!.detail.ownItem).toEqual({ shareConsent: false, published: false });
  expect(fits(created.json, 'OpportunityOut')).toEqual([]);
  const refused = await call('m4c', 'POST', '/api/items', { stream: 'tender', title: 'x', deadline: '7 Dec' });
  expect(refused.status).toBe(422);
  expect(refused.json!.errors).toEqual([{ field: 'deadline', message: 'include the year, for example 30 Nov 2026' }]);
  const feed = await call('m4c', 'GET', '/api/feed');
  const row = (feed.json!.items as { id: string }[]).find((i) => i.id === id);
  expect(fits(row, 'FeedItem')).toEqual([]);

  expect((await call('m4c', 'POST', '/api/items', { stream: 'tender', title: 'x', url: 'javascript:alert(1)' })).status).toBe(422);
  const edited = await call('m4c', 'PATCH', `/api/items/${id}`, { title: 'Fuel supply, phase 2' });
  expect(edited.json!.title).toBe('Fuel supply, phase 2');
  expect(fits(edited.json, 'OpportunityOut')).toEqual([]);
  expect((await call('m4c', 'PATCH', `/api/items/${id}`, { title: null })).status).toBe(422);

  expect((await call('m4c', 'POST', `/api/admin/catalogue/${id}/publish`)).status).toBe(409);
  expect((await call('m4c', 'GET', '/api/admin/catalogue?shareable=true')).json!.items).toEqual([]);
  const consent = await call('m4c', 'PUT', `/api/items/${id}/share-consent`, { allow: true });
  expect(consent.json).toEqual({ allow: true, published: false });
  expect(fits(consent.json, 'ShareConsentOut')).toEqual([]);
  const shareable = await call('m4c', 'GET', '/api/admin/catalogue?shareable=true');
  expect(fits(shareable.json, 'CataloguePage')).toEqual([]);
  expect((shareable.json!.items as { id: string }[]).map((i) => i.id)).toEqual([id]);
  const published = await call('m4c', 'POST', `/api/admin/catalogue/${id}/publish`);
  expect(published.status).toBe(200);
  expect(fits({ total: 1, items: [published.json] }, 'CataloguePage')).toEqual([]);
  const after = await call('m4c', 'GET', `/api/opportunities/${id}`);
  expect(fits(after.json, 'OpportunityOut')).toEqual([]);
  expect(after.json!.detail.ownItem).toEqual({ shareConsent: true, published: true });
  expect(after.json!.detail.changes[0]).toMatchObject({ field: 'visibility', new: { visibility: 'public' } });
  expect(JSON.stringify(after.json!.detail.changes)).not.toMatch(/_by/);
  // Once public: no withdrawing, no edits, no deleting.
  expect((await call('m4c', 'PUT', `/api/items/${id}/share-consent`, { allow: false })).status).toBe(409);
  expect((await call('m4c', 'PATCH', `/api/items/${id}`, { title: 'x' })).status).toBe(409);
  expect((await call('m4c', 'DELETE', `/api/items/${id}`)).status).toBe(409);

  const other = (await call('m4c', 'POST', '/api/items', { stream: 'event', title: 'Expo', eventStart: '2026-12-01' })).json!.id as string;
  expect((await call('m4c', 'DELETE', `/api/items/${other}`)).status).toBe(204);
  expect((await call('m4c', 'GET', `/api/opportunities/${other}`)).status).toBe(404);
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
  expect(await ids('?status=closing_soon')).toEqual(['abh-summit', 'wfp-logistics']);
  expect(await ids('?status=open&status=closing_soon')).toEqual(['abh-summit', 't2s-call', 'tbond-5y', 'wfp-logistics']);
  expect((await call('m4d', 'GET', '/api/feed?fit=7')).status).toBe(422);
});
