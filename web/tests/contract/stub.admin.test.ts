// @vitest-environment node
/**
 * The e2e stub's source and admin routes (tests/e2e/stubApi.ts) answer with the
 * keys of the API's models. These models are not in api-schemas.json yet (the
 * dump covers the member API); the key lists below are copied from
 * api/blackkite/routes/source_schemas.py and routes/schemas.py, and the catalogue
 * from routes/catalogue.py. When the dump gains them, check against it instead.
 */
import { afterAll, beforeAll, expect, test } from 'vitest';
import { startStubApi, STUB_COOKIE } from '../e2e/stubApi';

const KEYS = {
  SourceOut: 'id name home_url publisher streams kind collector_type config schedule effective_schedule rate_limit access_note status added_by created_at updated_at config_changed_at health last_success_at last_run_at items_30d promotion_runs',
  MemberSourceOut: 'id name home_url publisher kind streams last_success_at items_30d health muted',
  RunOut: 'id started_at finished_at status items_found items_new items_failed error',
  PreviewOut: 'ok error items total_parsed requests_made elapsed_seconds',
  PreviewItemOut: 'url title organisation listed_published listed_deadline snippet detail_url extra',
  SuggestionOut: 'id url note status created_at reviewed_at source_id',
  AdminSuggestionOut: 'id url note status created_at reviewed_at source_id user_id reviewed_by',
  UserOut: 'id email name role status created_at',
  InviteOut: 'id email invited_by created_at expires_at accepted_at status',
  CatalogueItem: 'id stream title organisation status verification trust needsReview reviewReasons deadline memberVisible sources createdAt updatedAt',
} as const;
const keys = (o: unknown) => Object.keys(o as object).sort();
const expected = (m: keyof typeof KEYS) => KEYS[m].split(' ').sort();

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

test('member source routes: the API models\' keys', async () => {
  const sources = (await call('c1', 'GET', '/api/sources')).json as unknown[];
  expect(sources.length).toBeGreaterThan(0);
  for (const s of sources) expect(keys(s)).toEqual(expected('MemberSourceOut'));
  const sent = await call('c1', 'POST', '/api/source-suggestions', { url: 'https://www.rdb.rw/', note: null });
  expect(sent.status).toBe(201);
  expect(keys(sent.json)).toEqual(expected('SuggestionOut'));
  expect((await call('c1', 'POST', '/api/source-suggestions', { url: 'https://www.rdb.rw/', why: 'x' })).status).toBe(422);
});

test('admin routes: the API models\' keys', async () => {
  const list = (await call('c2', 'GET', '/api/admin/sources')).json as unknown[];
  for (const s of list) expect(keys(s)).toEqual(expected('SourceOut'));
  const created = await call('c2', 'POST', '/api/admin/sources', { name: 'New', home_url: 'https://n.rw/', streams: ['event'], kind: 'news', collector_type: 'rss', config: { feed_url: 'https://n.rw/feed' } });
  expect(created.status).toBe(201);
  expect(keys(created.json)).toEqual(expected('SourceOut'));
  expect((created.json as { status: string }).status).toBe('testing');
  const runs = (await call('c2', 'GET', '/api/admin/sources/src-umucyo/runs')).json as unknown[];
  for (const r of runs) expect(keys(r)).toEqual(expected('RunOut'));
  const preview = (await call('c2', 'POST', '/api/admin/sources/test-run', { collector_type: 'rss', config: { feed_url: 'https://n.rw/feed' }, home_url: null, streams: ['tender'], rate_limit: null })).json as { items: unknown[] };
  expect(keys(preview)).toEqual(expected('PreviewOut'));
  for (const i of preview.items) expect(keys(i)).toEqual(expected('PreviewItemOut'));
  for (const s of (await call('c2', 'GET', '/api/admin/source-suggestions')).json as unknown[]) expect(keys(s)).toEqual(expected('AdminSuggestionOut'));
  for (const u of (await call('c2', 'GET', '/api/admin/users')).json as unknown[]) expect(keys(u)).toEqual(expected('UserOut'));
  const invite = await call('c2', 'POST', '/api/admin/invites', { email: 'grace@example.rw' });
  expect(keys(invite.json)).toEqual(expected('InviteOut'));
  const page = (await call('c2', 'GET', '/api/admin/catalogue?needsReview=true')).json as { total: number; items: unknown[] };
  for (const i of page.items) expect(keys(i)).toEqual(expected('CatalogueItem'));
  const types = (await call('c2', 'GET', '/api/admin/collector-types')).json as { type: string; fields: { name: string; type: string; required: boolean; help: string | null }[] }[];
  expect(types.map((t) => t.type)).toEqual(['rss', 'html_list', 'browser_list', 'json_api', 'search_query', 'email_ingest', 'custom']);
  for (const t of types) for (const f of t.fields) expect(Object.keys(f).sort()).toEqual(['help', 'name', 'required', 'type']);
});

test('the promotion gate and the old /admin paths', async () => {
  const refused = await call('c3', 'POST', '/api/admin/sources/src-umucyo/status', { status: 'active' });
  expect(refused.status).toBe(409);
  expect((await call('c3', 'GET', '/admin/sources')).status).toBe(404);
});

test('a member gets 403 from every admin route', async () => {
  await fetch(`${base}/__stub/sessions/m1`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ role: 'member' }) });
  for (const path of ['/api/admin/sources', '/api/admin/collector-types', '/api/admin/users', '/api/admin/catalogue']) {
    expect((await call('m1', 'GET', path)).status, path).toBe(403);
  }
  expect(((await call('m1', 'GET', '/me')).json as { role: string }).role).toBe('member');
});
