// @vitest-environment node
/**
 * The e2e stub's source and admin routes (tests/e2e/stubApi.ts) answer in the
 * API's real shapes (docs/api-contract.md section 4.1), checked against the
 * models dumped into api-schemas.json; and what the screens send is what the API
 * accepts (SourceIn, SourcePatch, PreviewIn, StatusIn, SuggestionIn, UserPatch).
 * The bodies below are the ones src/screens/admin/sourceForm.test.ts pins for
 * `validate()` (this file runs under the node tsconfig, without the app's JSX).
 */
import { afterAll, beforeAll, expect, test } from 'vitest';
import { startStubApi, STUB_COOKIE } from '../e2e/stubApi';
import dump from './api-schemas.json' with { type: 'json' };
import { check, type Schema } from './schemaCheck';

const schemas = dump.schemas as unknown as Record<string, Schema>;
const opts = { omitIfNone: dump.omitIfNone as Record<string, string[]> };
const fits = (value: unknown, model: string) => {
  expect(schemas[model], model).toBeDefined();
  return check(value, schemas[model]!, opts);
};

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
  return { status: res.status, json: text ? (JSON.parse(text) as unknown) : undefined };
}

test('the schema file has the admin models', () => {
  for (const m of ['SourceOut', 'SourceDetailOut', 'MemberSourceOut', 'RunPage', 'PreviewOut', 'CollectorTypeOut', 'SuggestionOut', 'AdminSuggestionOut', 'AdminUserOut', 'InviteOut', 'CataloguePage', 'SourceIn', 'SourcePatch', 'PreviewIn', 'StatusIn', 'SuggestionIn', 'UserPatch']) {
    expect(schemas[m], m).toBeDefined();
  }
});

test('member source routes', async () => {
  const sources = (await call('c1', 'GET', '/api/sources')).json as unknown[];
  expect(sources.length).toBeGreaterThan(0);
  for (const s of sources) expect(fits(s, 'MemberSourceOut')).toEqual([]);
  const body = { url: 'https://www.rdb.rw/', note: 'Covers: RDB calls\nWhy it is useful: Funding' };
  expect(fits(body, 'SuggestionIn')).toEqual([]);
  const sent = await call('c1', 'POST', '/api/source-suggestions', body);
  expect(sent.status).toBe(201);
  expect(fits(sent.json, 'SuggestionOut')).toEqual([]);
  for (const s of (await call('c1', 'GET', '/api/source-suggestions')).json as unknown[]) expect(fits(s, 'SuggestionOut')).toEqual([]);
  expect((await call('c1', 'POST', '/api/source-suggestions', { url: 'https://www.rdb.rw/', why: 'x' })).status).toBe(422);
});

test('admin source routes, with the bodies the editor builds', async () => {
  for (const s of (await call('c2', 'GET', '/api/admin/sources')).json as unknown[]) expect(fits(s, 'SourceOut')).toEqual([]);
  const types = (await call('c2', 'GET', '/api/admin/collector-types')).json as { type: string }[];
  expect(types.map((t) => t.type)).toEqual(['rss', 'html_list', 'browser_list', 'json_api', 'search_query', 'email_ingest', 'custom']);
  for (const t of types) expect(fits(t, 'CollectorTypeOut')).toEqual([]);

  const body = {
    name: 'New',
    homeUrl: 'https://n.rw/',
    publisher: null,
    streams: ['event'],
    kind: 'news',
    collectorType: 'rss',
    config: { feed_url: 'https://n.rw/feed' },
    schedule: null,
    rateLimit: 2,
    accessNote: null,
  };
  expect(fits(body, 'SourceIn')).toEqual([]);
  expect(fits({ ...body, suggestionId: 'sg-1' }, 'SourceIn')).toEqual([]);
  expect(fits(body, 'SourcePatch')).toEqual([]);
  const preview = { collectorType: 'rss', config: { feed_url: 'https://n.rw/feed' }, homeUrl: null, streams: ['tender'], rateLimit: null };
  expect(fits(preview, 'PreviewIn')).toEqual([]);
  const ran = await call('c2', 'POST', '/api/admin/sources/test-run', preview);
  expect(fits(ran.json, 'PreviewOut')).toEqual([]);
  expect(fits((await call('c2', 'POST', '/api/admin/sources/src-umucyo/test-run')).json, 'PreviewOut')).toEqual([]);
  // An email_ingest test run that skipped an email: PreviewOut.warnings, same shape as a run's.
  const mail = { collectorType: 'email_ingest', config: { sender: 'alerts@jobinrwanda.com' }, homeUrl: null, streams: ['tender'], rateLimit: null };
  const mailed = (await call('c2', 'POST', '/api/admin/sources/test-run', mail)).json as { warnings: { kind: string }[] };
  expect(fits(mailed, 'PreviewOut')).toEqual([]);
  expect(mailed.warnings.map((w) => w.kind)).toEqual(['email_no_link']);

  const created = await call('c2', 'POST', '/api/admin/sources', body);
  expect(created.status).toBe(201);
  expect(fits(created.json, 'SourceDetailOut')).toEqual([]);
  const id = (created.json as { id: string }).id;
  expect((created.json as { status: string }).status).toBe('testing');
  expect(fits((await call('c2', 'GET', `/api/admin/sources/${id}`)).json, 'SourceDetailOut')).toEqual([]);
  expect(fits((await call('c2', 'PATCH', `/api/admin/sources/${id}`, { config: { feed_url: 'https://n.rw/rss' } })).json, 'SourceDetailOut')).toEqual([]);
  expect(fits({ status: 'paused' }, 'StatusIn')).toEqual([]);
  const paused = await call('c2', 'POST', `/api/admin/sources/${id}/status`, { status: 'paused' });
  expect(fits(paused.json, 'SourceDetailOut')).toEqual([]);
  expect((paused.json as { statusHistory: unknown[] }).statusHistory).toHaveLength(2);

  const runs = (await call('c2', 'GET', '/api/admin/sources/src-umucyo/runs?limit=20')).json as { total: number };
  expect(fits(runs, 'RunPage')).toEqual([]);
  expect(runs.total).toBe(2);
  const failed = (await call('c2', 'GET', '/api/admin/sources/src-umucyo/runs?status=failed&limit=20')).json as { items: { status: string }[] };
  expect(failed.items.map((r) => r.status)).toEqual(['failed']);
  // problems=true (the error log): failed runs and runs that succeeded with warnings.
  const problems = (await call('c2', 'GET', '/api/admin/sources/src-umucyo/runs?problems=true&limit=20')).json as { items: { status: string; warnings: unknown[] }[] };
  expect(fits(problems, 'RunPage')).toEqual([]);
  expect(problems.items.map((r) => [r.status, r.warnings.length])).toEqual([['succeeded', 1], ['failed', 0]]);
});

test('the promotion gate refuses with its numbers; old /admin API paths are gone', async () => {
  const refused = await call('c3', 'POST', '/api/admin/sources/src-umucyo/status', { status: 'active' });
  expect(refused.status).toBe(409);
  expect(refused.json).toEqual({ detail: expect.stringMatching(/^This source needs 2 .* it has 1\.$/), errors: [], goodRuns: 1, needed: 2 });
  expect((await call('c3', 'GET', '/admin/sources')).status).toBe(404);
});

test('refusals answer {detail, errors} like RefusalOut: private addresses, a taken name, missing fields; 429s carry a detail', async () => {
  const field = { field: 'config.feed_url', message: 'address 127.0.0.1 is not public' };
  const ran = await call('c5', 'POST', '/api/admin/sources/test-run', { collectorType: 'rss', config: { feed_url: 'http://127.0.0.1/feed' }, homeUrl: null, streams: ['tender'], rateLimit: null });
  expect(ran).toEqual({ status: 422, json: { detail: 'Feed URL: address 127.0.0.1 is not public.', errors: [field] } });
  const body = { name: 'X', homeUrl: 'http://10.0.0.1/', streams: ['event'], kind: 'news', collectorType: 'rss', config: { feed_url: 'http://127.0.0.1/feed' } };
  expect((await call('c5', 'POST', '/api/admin/sources', body)).json).toEqual({
    detail: 'Home page: address 10.0.0.1 is not public. Feed URL: address 127.0.0.1 is not public.',
    errors: [{ field: 'homeUrl', message: 'address 10.0.0.1 is not public' }, field],
  });
  const missing = await call('c5', 'POST', '/api/admin/sources', { name: 'Y' });
  expect(missing.status).toBe(422);
  expect((missing.json as { errors: { field: string }[] }).errors.map((e) => e.field)).toEqual(['homeUrl', 'streams', 'kind', 'collectorType']);
  const taken = await call('c5', 'PATCH', '/api/admin/sources/src-umucyo', { name: 'RSE bond market' });
  expect(taken).toEqual({ status: 409, json: { detail: 'Name: a source with that name already exists.', errors: [{ field: 'name', message: 'a source with that name already exists' }] } });

  // A stored config the API refuses: PreviewOut with errors.
  const sources = (await call('c5', 'GET', '/api/admin/sources')).json as Record<string, unknown>[];
  const umucyo = sources.find((x) => x.id === 'src-umucyo')!;
  await fetch(`${base}/__stub/sessions/c7`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sources: [{ ...umucyo, config: { list_url: 'http://127.0.0.1/', selectors: { item: 'tr', title: 'a' } } }] }),
  });
  const saved = await call('c7', 'POST', '/api/admin/sources/src-umucyo/test-run');
  expect(fits(saved.json, 'PreviewOut')).toEqual([]);
  expect(saved.json).toMatchObject({ ok: false, error: 'List URL: address 127.0.0.1 is not public.', errors: [{ field: 'config.list_url', message: 'address 127.0.0.1 is not public' }] });

  await fetch(`${base}/__stub/sessions/c6`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ testRunBusy: true, suggestionsPerDay: 0 }) });
  expect(await call('c6', 'POST', '/api/admin/sources/src-umucyo/test-run')).toEqual({ status: 429, json: { detail: 'Another test run is in progress; try again in a minute.' } });
  expect((await call('c6', 'POST', '/api/source-suggestions', { url: 'https://www.rdb.rw/' })).status).toBe(429);
});

test('suggestions, review, users and invites', async () => {
  for (const s of (await call('c4', 'GET', '/api/admin/source-suggestions')).json as unknown[]) expect(fits(s, 'AdminSuggestionOut')).toEqual([]);
  expect(fits((await call('c4', 'POST', '/api/admin/source-suggestions/sg-1/accept')).json, 'AdminSuggestionOut')).toEqual([]);
  expect(fits((await call('c4', 'GET', '/api/admin/catalogue?needsReview=true')).json, 'CataloguePage')).toEqual([]);
  const users = (await call('c4', 'GET', '/api/admin/users')).json as unknown[];
  for (const u of users) expect(fits(u, 'AdminUserOut')).toEqual([]);
  expect(fits({ role: 'admin' }, 'UserPatch')).toEqual([]);
  expect(fits((await call('c4', 'PATCH', '/api/admin/users/u2', { role: 'admin' })).json, 'AdminUserOut')).toEqual([]);
  expect((await call('c4', 'PATCH', '/api/admin/users/u1', { role: 'member' })).status).toBe(400);
  const invite = await call('c4', 'POST', '/api/admin/invites', { email: 'grace@example.rw' });
  expect(fits(invite.json, 'InviteOut')).toEqual([]);
  for (const i of (await call('c4', 'GET', '/api/admin/invites')).json as unknown[]) expect(fits(i, 'InviteOut')).toEqual([]);
  expect(fits((await call('c4', 'POST', '/api/admin/users/u2/deactivate')).json, 'AdminUserOut')).toEqual([]);
});

test('a member gets 403 from every admin route', async () => {
  await fetch(`${base}/__stub/sessions/m1`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ role: 'member' }) });
  for (const path of ['/api/admin/sources', '/api/admin/collector-types', '/api/admin/users', '/api/admin/catalogue']) {
    expect((await call('m1', 'GET', path)).status, path).toBe(403);
  }
  expect(((await call('m1', 'GET', '/me')).json as { role: string }).role).toBe('member');
});
