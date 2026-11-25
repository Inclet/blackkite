import { afterEach, expect, test, vi } from 'vitest';
import { api, ApiError, refusalOf, request } from './client';

afterEach(() => vi.unstubAllGlobals());

function reply(status: number, body?: unknown) {
  const text = body === undefined ? '' : typeof body === 'string' ? body : JSON.stringify(body);
  return new Response(status === 204 ? null : text, { status, headers: { 'Content-Type': 'application/json' } });
}

function stub(...responses: (Response | Error | DOMException)[]) {
  const fn = vi.fn();
  for (const r of responses) {
    if (!(r instanceof Response)) fn.mockRejectedValueOnce(r);
    else fn.mockResolvedValueOnce(r);
  }
  vi.stubGlobal('fetch', fn);
  return fn;
}

const call = (fn: ReturnType<typeof vi.fn>, i = 0) => {
  const [url, init] = fn.mock.calls[i]! as [string, RequestInit];
  return { url, init, body: init.body ? JSON.parse(init.body as string) : undefined, headers: init.headers as Record<string, string> };
};

test('GET: same-origin credentials, JSON accepted, no body, manual redirects', async () => {
  const fn = stub(reply(200, { user: { name: 'Clet' }, sources: { checked: 8, when: 'today' }, digest: { channel: 'email' }, items: [] }));
  const feed = await api.feed();
  expect(feed.user.name).toBe('Clet');
  const { url, init, headers } = call(fn);
  expect(url).toBe('/api/feed');
  expect(init.method).toBe('GET');
  expect(init.credentials).toBe('same-origin');
  expect(init.redirect).toBe('manual');
  expect(init.body).toBeUndefined();
  expect(headers).toEqual({ Accept: 'application/json' });
});

test('feed filters become the query string; empty ones are left out', async () => {
  const fn = stub(reply(200, { items: [] }));
  await api.feed({ stream: 'tender', profile: 'AI lab', window: '' });
  expect(call(fn).url).toBe('/api/feed?stream=tender&profile=AI+lab');
});

test.each([
  ['opportunity', () => api.opportunity('wfp/1'), '/api/opportunities/wfp%2F1', 'GET', undefined],
  ['state', () => api.setState('wfp', 'saved'), '/api/opportunities/wfp/state', 'PUT', { state: 'saved' }],
  ['dismiss with reason', () => api.setState('wfp', 'dismissed', 'too_small'), '/api/opportunities/wfp/state', 'PUT', { state: 'dismissed', dismissReason: 'too_small' }],
  ['note', () => api.setNote('wfp', 'Call Tuesday'), '/api/opportunities/wfp/note', 'PUT', { note: 'Call Tuesday' }],
  ['shortlist', () => api.shortlist(), '/api/shortlist', 'GET', undefined],
  ['profiles', () => api.profiles(), '/api/profiles', 'GET', undefined],
  ['create profile', () => api.createProfile({ name: 'X', type: 'business', data: { streams: ['tender'] } }), '/api/profiles', 'POST', { name: 'X', type: 'business', data: { streams: ['tender'] } }],
  ['update profile', () => api.updateProfile('p1', { name: 'Y' }), '/api/profiles/p1', 'PATCH', { name: 'Y' }],
  ['delete profile', () => api.deleteProfile('p1'), '/api/profiles/p1', 'DELETE', undefined],
  ['digest settings', () => api.digestSettings(), '/api/digest-settings', 'GET', undefined],
  [
    'save digest settings',
    () => api.saveDigestSettings({ channel: 'email', frequency: 'off', day: 'mon', alertMinFit: null, streams: null }),
    '/api/digest-settings',
    'PUT',
    { channel: 'email', frequency: 'off', day: 'mon', alertMinFit: null, streams: null },
  ],
  ['me', () => api.me(), '/me', 'GET', undefined],
  ['export', () => api.exportMe(), '/api/me/export', 'GET', undefined],
  ['delete account', () => api.deleteMe(), '/api/me', 'DELETE', undefined],
  ['request link', () => api.requestLink('a@b.rw'), '/auth/request-link', 'POST', { email: 'a@b.rw' }],
  ['logout', () => api.logout(), '/auth/logout', 'POST', undefined],
])('%s: %s %s', async (_name, run, url, method, body) => {
  const fn = stub(reply(200, {}));
  await run();
  const c = call(fn);
  expect(c.url).toBe(url);
  expect(c.init.method).toBe(method);
  expect(c.body).toEqual(body);
  if (body !== undefined) expect(c.headers['Content-Type']).toBe('application/json');
});

test('204 and empty bodies resolve to undefined', async () => {
  stub(reply(204), reply(200, ''));
  await expect(api.deleteProfile('p')).resolves.toBeUndefined();
  await expect(request('/me')).resolves.toBeUndefined();
});

test.each([
  [401, 'unauthorized'],
  [403, 'forbidden'],
  [404, 'not-found'],
  [400, 'invalid'],
  [422, 'invalid'],
  [409, 'conflict'],
  [429, 'too-many'],
  [500, 'unreachable'],
  [502, 'unreachable'],
  [302, 'unreachable'],
])('%i is an ApiError of kind %s, with the detail kept', async (status, kind) => {
  stub(reply(status, { detail: 'why' }));
  const err = await api.me().catch((e: unknown) => e);
  expect(err).toBeInstanceOf(ApiError);
  expect(err).toMatchObject({ kind, status, detail: 'why' });
});

test('a network failure and a body that is not JSON are "unreachable"', async () => {
  stub(new TypeError('offline'), reply(200, '<html>'));
  await expect(api.me()).rejects.toMatchObject({ kind: 'unreachable', status: 0 });
  await expect(api.me()).rejects.toMatchObject({ kind: 'unreachable', status: 200 });
});

test('an aborted request rejects with the AbortError, not an ApiError', async () => {
  stub(new DOMException('aborted', 'AbortError'));
  const err = await api.feed({}, new AbortController().signal).catch((e: unknown) => e);
  expect(err).not.toBeInstanceOf(ApiError);
  expect((err as DOMException).name).toBe('AbortError');
});

test('a refusal keeps the whole answer: detail, field errors and any extra numbers', async () => {
  stub(
    reply(422, {
      detail: 'Feed URL: address 127.0.0.1 is not public.',
      errors: [{ field: 'config.feed_url', message: 'address 127.0.0.1 is not public' }, { field: null, message: 'x' }, { nope: 1 }],
    }),
    reply(409, { detail: 'Needs 2 good runs.', errors: [], goodRuns: 1, needed: 2 }),
    reply(429, 'not json'),
  );
  const first = (await request('/api/admin/sources', { method: 'POST', body: {} }).catch((e: unknown) => e)) as ApiError;
  expect(first.kind).toBe('invalid');
  expect(refusalOf(first)).toEqual({
    detail: 'Feed URL: address 127.0.0.1 is not public.',
    errors: [
      { field: 'config.feed_url', message: 'address 127.0.0.1 is not public' },
      { field: null, message: 'x' },
    ],
  });
  const second = (await request('/x', { method: 'POST' }).catch((e: unknown) => e)) as ApiError;
  expect(second.kind).toBe('conflict');
  expect(second.body).toEqual({ detail: 'Needs 2 good runs.', errors: [], goodRuns: 1, needed: 2 });
  const third = (await request('/x', { method: 'POST' }).catch((e: unknown) => e)) as ApiError;
  expect(third.kind).toBe('too-many');
  expect(refusalOf(third)).toEqual({ detail: null, errors: [] });
});
