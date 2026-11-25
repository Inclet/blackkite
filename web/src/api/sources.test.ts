import { afterEach, expect, test, vi } from 'vitest';
import { mockApi } from '../test/mockApi';
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

test('collector types: a list or a map, snake or camel case, required defaults to false', () => {
  const field = { name: 'feed_url', type: 'url', required: true, help: 'The feed address' };
  expect(collectorTypesFrom([{ type: 'rss', label: 'RSS feed', fields: [field] }])).toEqual([
    { type: 'rss', label: 'RSS feed', fields: [{ name: 'feed_url', type: 'url', required: true, help: 'The feed address', label: null }] },
  ]);
  expect(collectorTypesFrom({ custom: { fields: [{ name: 'class_name' }] }, rss: [field] })).toEqual([
    { type: 'custom', label: null, fields: [{ name: 'class_name', type: 'string', required: false, help: null, label: null }] },
    { type: 'rss', label: null, fields: [{ ...field, label: null }] },
  ]);
  expect(collectorTypesFrom([{ collector_type: 'json_api', fields: [] }])[0]!.type).toBe('json_api');
  expect(collectorTypesFrom(null)).toEqual([]);
});

test('paths: members under /api, admins under /api/admin; bodies as the API takes them', async () => {
  const api = mockApi({
    'GET /api/sources': [{ id: 's', home_url: 'h', items_30d: 2 }],
    'POST /api/sources/s/mute': undefined,
    'DELETE /api/sources/s/mute': undefined,
    'POST /api/source-suggestions': { id: 'g', url: 'https://x.rw', status: 'suggested', created_at: 't' },
    'GET /api/admin/sources/s': { id: 's', promotion_runs: 1, config: { list_url: 'u' } },
    'POST /api/admin/sources/s/status': { id: 's', status: 'paused' },
    'POST /api/admin/sources/test-run': { ok: true, items: [], total_parsed: 0 },
    'GET /api/admin/collector-types': [{ type: 'rss', fields: [] }],
    'GET /api/admin/catalogue': { total: 0, items: [] },
    'POST /api/admin/invites': { id: 'i', email: 'a@b.rw' },
  });
  expect(await sourcesApi.sources()).toEqual([{ id: 's', homeUrl: 'h', items30d: 2 }]);
  await sourcesApi.mute('s');
  await sourcesApi.unmute('s');
  expect((await sourcesApi.suggest('https://x.rw', 'note')).createdAt).toBe('t');
  expect(await sourcesApi.adminSource('s')).toEqual({ id: 's', promotionRuns: 1, config: { list_url: 'u' } });
  await sourcesApi.setStatus('s', 'paused');
  expect((await sourcesApi.testRun({ collector_type: 'rss', config: {}, home_url: null, streams: ['tender'], rate_limit: null })).totalParsed).toBe(0);
  expect(await sourcesApi.collectorTypes()).toEqual([{ type: 'rss', label: null, fields: [] }]);
  await sourcesApi.reviewQueue();
  await sourcesApi.invite('a@b.rw');
  expect(api.calls).toEqual([
    { key: 'GET /api/sources', body: undefined },
    { key: 'POST /api/sources/s/mute', body: undefined },
    { key: 'DELETE /api/sources/s/mute', body: undefined },
    { key: 'POST /api/source-suggestions', body: { url: 'https://x.rw', note: 'note' } },
    { key: 'GET /api/admin/sources/s', body: undefined },
    { key: 'POST /api/admin/sources/s/status', body: { status: 'paused' } },
    { key: 'POST /api/admin/sources/test-run', body: { collector_type: 'rss', config: {}, home_url: null, streams: ['tender'], rate_limit: null } },
    { key: 'GET /api/admin/collector-types', body: undefined },
    { key: 'GET /api/admin/catalogue', body: undefined },
    { key: 'POST /api/admin/invites', body: { email: 'a@b.rw' } },
  ]);
  expect(api.fetch.mock.calls[8]![0]).toBe('/api/admin/catalogue?needsReview=true');
});
