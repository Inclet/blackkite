import { afterEach, expect, test, vi } from 'vitest';
import { m4Api } from './m4';

afterEach(() => vi.unstubAllGlobals());

function stub(body: unknown = {}, status = 200) {
  const fn = vi.fn(async () => new Response(status === 204 ? null : JSON.stringify(body), { status }));
  vi.stubGlobal('fetch', fn);
  return fn;
}
const call = (fn: ReturnType<typeof vi.fn>) => {
  const [url, init] = fn.mock.calls[0]! as [string, RequestInit];
  return { url, method: init.method, body: init.body ? JSON.parse(init.body as string) : undefined };
};

test.each([
  ['calendar', () => m4Api.calendar({ from: '2026-11-01', to: '2026-11-30', kind: 'all', saved: false }), '/api/calendar?from=2026-11-01&to=2026-11-30&kind=all', 'GET', undefined],
  ['calendar, saved only', () => m4Api.calendar({ from: '2026-12-01', to: '2026-12-31', kind: 'deadlines', saved: true }), '/api/calendar?from=2026-12-01&to=2026-12-31&kind=deadlines&saved=true', 'GET', undefined],
  ['feed link', () => m4Api.feedLink(), '/api/calendar/feed-link', 'GET', undefined],
  ['rotate', () => m4Api.rotateFeedLink(), '/api/calendar/feed-link/rotate', 'POST', undefined],
  ['create item', () => m4Api.createItem({ stream: 'tender', title: 'X' }), '/api/items', 'POST', { stream: 'tender', title: 'X' }],
  ['update item', () => m4Api.updateItem('a/b', { title: 'Y' }), '/api/items/a%2Fb', 'PATCH', { title: 'Y' }],
  ['delete item', () => m4Api.deleteItem('a'), '/api/items/a', 'DELETE', undefined],
  ['consent', () => m4Api.setShareConsent('a', true), '/api/items/a/share-consent', 'PUT', { allow: true }],
  ['shareable', () => m4Api.shareable(), '/api/admin/catalogue?shareable=true', 'GET', undefined],
  ['publish', () => m4Api.publish('a'), '/api/admin/catalogue/a/publish', 'POST', undefined],
])('%s', async (_n, run, url, method, body) => {
  const fn = stub();
  await run();
  expect(call(fn)).toEqual({ url, method, body });
});

test('a 409 from publish is a conflict', async () => {
  stub({ detail: 'no consent' }, 409);
  await expect(m4Api.publish('a')).rejects.toMatchObject({ kind: 'conflict' });
});
