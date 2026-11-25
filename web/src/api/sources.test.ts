import { afterEach, expect, test, vi } from 'vitest';
import { mockApi } from '../test/mockApi';
import REAL_TYPES from '../../tests/fixtures/collector-types.json';
import { camel, collectorTypesFrom, sourcesApi } from './sources';

afterEach(() => vi.unstubAllGlobals());

test('camel(): snake_case keys become camelCase, deeply; config and extra values are left as sent', () => {
  expect(
    camel({
      home_url: 'https://x.rw',
      items_30d: 3,
      last_success_at: null,
      config: { list_url: 'https://x.rw/t', selectors: { item_css: 'li' } },
      items: [{ listed_deadline: '1 Dec', extra: { tender_ref: 'A' } }],
      alreadyCamel: 1,
    }),
  ).toEqual({
    homeUrl: 'https://x.rw',
    items30d: 3,
    lastSuccessAt: null,
    config: { list_url: 'https://x.rw/t', selectors: { item_css: 'li' } },
    items: [{ listedDeadline: '1 Dec', extra: { tender_ref: 'A' } }],
    alreadyCamel: 1,
  });
});

test('collector types (contract 4.1): the real API answer reads with kinds, nested fields, options, defaults and bounds', () => {
  const types = collectorTypesFrom(REAL_TYPES);
  expect(types.map((t) => [t.type, t.implemented, t.schemaSource])).toEqual(REAL_TYPES.map((t) => [t.type, t.implemented, t.schemaSource]));
  // Every field arrives as sent (plus label: null), at every depth.
  const withLabel = (fields: unknown[]): unknown[] =>
    fields.map((f) => {
      const o = f as Record<string, unknown>;
      return { ...o, label: null, fields: Array.isArray(o.fields) ? withLabel(o.fields) : null };
    });
  for (const [i, t] of types.entries()) expect(t.fields).toEqual(withLabel(REAL_TYPES[i]!.fields));
  const html = types.find((t) => t.type === 'html_list')!;
  expect(html.fields.find((f) => f.name === 'max_pages')).toMatchObject({ kind: 'integer', default: 1, min: 1, max: 20 });
  expect(html.fields.find((f) => f.name === 'selectors')!.fields!.find((f) => f.name === 'title')).toMatchObject({ kind: 'selector', required: true });
  expect(types.find((t) => t.type === 'email_ingest')!.fields.find((f) => f.name === 'parse_mode')).toMatchObject({ kind: 'choice', options: ['links', 'message'] });
});

test('collector types: a declared (not built) type, a map keyed by type, older `type` keys, and nothing', () => {
  const declared = { type: 'rss', implemented: false, schemaSource: 'declared', fields: [{ name: 'feed_url', kind: 'url', required: true, help: 'Feed' }] };
  expect(collectorTypesFrom([declared])[0]).toMatchObject({ type: 'rss', implemented: false, schemaSource: 'declared', fields: [{ name: 'feed_url', kind: 'url', required: true, default: null }] });
  expect(collectorTypesFrom({ custom: [{ name: 'class_name', type: 'string' }] })[0]).toMatchObject({ type: 'custom', fields: [{ name: 'class_name', kind: 'string', required: false, help: null }] });
  expect(collectorTypesFrom(null)).toEqual([]);
});

test('paths: members under /api, admins under /api/admin; bodies as the API takes them', async () => {
  const api = mockApi({
    'GET /api/sources': [{ id: 's', homeUrl: 'h', items30d: 2 }],
    'GET /api/admin/sources/s/runs': { total: 3, items: [{ id: 'r', status: 'failed' }] },
    'POST /api/sources/s/mute': undefined,
    'DELETE /api/sources/s/mute': undefined,
    'POST /api/source-suggestions': { id: 'g', url: 'https://x.rw', status: 'suggested', created_at: 't' },
    'GET /api/admin/sources/s': { id: 's', promotion_runs: 1, config: { list_url: 'u' } },
    'POST /api/admin/sources/s/status': { id: 's', status: 'paused' },
    'POST /api/admin/sources/test-run': { ok: true, items: [], totalParsed: 0 },
    'GET /api/admin/collector-types': [{ type: 'rss', implemented: false, schemaSource: 'declared', fields: [] }],
    'PATCH /api/admin/users/u2': { id: 'u2', role: 'admin' },
    'GET /api/admin/catalogue': { total: 0, items: [] },
    'POST /api/admin/invites': { id: 'i', email: 'a@b.rw' },
  });
  expect(await sourcesApi.sources()).toEqual([{ id: 's', homeUrl: 'h', items30d: 2 }]);
  await sourcesApi.mute('s');
  await sourcesApi.unmute('s');
  expect((await sourcesApi.suggest('https://x.rw', 'note')).createdAt).toBe('t');
  expect(await sourcesApi.adminSource('s')).toEqual({ id: 's', promotionRuns: 1, config: { list_url: 'u' } });
  await sourcesApi.setStatus('s', 'paused');
  expect((await sourcesApi.testRun({ collectorType: 'rss', config: {}, homeUrl: null, streams: ['tender'], rateLimit: null })).totalParsed).toBe(0);
  expect(await sourcesApi.collectorTypes()).toEqual([{ type: 'rss', label: null, implemented: false, schemaSource: 'declared', fields: [] }]);
  await sourcesApi.reviewQueue();
  await sourcesApi.invite('a@b.rw');
  expect(await sourcesApi.runs('s', { failed: true })).toEqual({ total: 3, items: [{ id: 'r', status: 'failed' }] });
  expect((await sourcesApi.setRole('u2', 'admin')).role).toBe('admin');
  expect(api.calls).toEqual([
    { key: 'GET /api/sources', body: undefined },
    { key: 'POST /api/sources/s/mute', body: undefined },
    { key: 'DELETE /api/sources/s/mute', body: undefined },
    { key: 'POST /api/source-suggestions', body: { url: 'https://x.rw', note: 'note' } },
    { key: 'GET /api/admin/sources/s', body: undefined },
    { key: 'POST /api/admin/sources/s/status', body: { status: 'paused' } },
    { key: 'POST /api/admin/sources/test-run', body: { collectorType: 'rss', config: {}, homeUrl: null, streams: ['tender'], rateLimit: null } },
    { key: 'GET /api/admin/collector-types', body: undefined },
    { key: 'GET /api/admin/catalogue', body: undefined },
    { key: 'POST /api/admin/invites', body: { email: 'a@b.rw' } },
    { key: 'GET /api/admin/sources/s/runs', body: undefined },
    { key: 'PATCH /api/admin/users/u2', body: { role: 'admin' } },
  ]);
  expect(api.fetch.mock.calls[10]![0]).toBe('/api/admin/sources/s/runs?status=failed&limit=20');
  expect(api.fetch.mock.calls[8]![0]).toBe('/api/admin/catalogue?needsReview=true');
});
