import { afterEach, expect, test, vi } from 'vitest';
import { api, ApiError, request } from './client';

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
  expect(url).toBe('/feed');
  expect(init.method).toBe('GET');
  expect(init.credentials).toBe('same-origin');
  expect(init.redirect).toBe('manual');
  expect(init.body).toBeUndefined();
  expect(headers).toEqual({ Accept: 'application/json' });
});

test('feed filters become the query string; empty ones are left out', async () => {
  const fn = stub(reply(200, { items: [] }));
  await api.feed({ stream: 'tender', profile: 'AI lab', window: '' });
  expect(call(fn).url).toBe('/feed?stream=tender&profile=AI+lab');
});

test.each([
  ['opportunity', () => api.opportunity('wfp/1'), '/opportunities/wfp%2F1', 'GET', undefined],
  ['state', () => api.setState('wfp', 'saved'), '/opportunities/wfp/state', 'PUT', { state: 'saved' }],
  ['dismiss with reason', () => api.setState('wfp', 'dismissed', 'Too far'), '/opportunities/wfp/state', 'PUT', { state: 'dismissed', dismissReason: 'Too far' }],
  ['note', () => api.setNote('wfp', 'Call Tuesday'), '/opportunities/wfp/note', 'PUT', { note: 'Call Tuesday' }],
  ['shortlist', () => api.shortlist(), '/shortlist', 'GET', undefined],
  ['profiles', () => api.profiles(), '/profiles', 'GET', undefined],
  ['create profile', () => api.createProfile({ name: 'X', type: 'business', data: {} }), '/profiles', 'POST', { name: 'X', type: 'business', data: {} }],
  ['update profile', () => api.updateProfile('p1', { name: 'Y' }), '/profiles/p1', 'PATCH', { name: 'Y' }],
  ['delete profile', () => api.deleteProfile('p1'), '/profiles/p1', 'DELETE', undefined],
  ['digest settings', () => api.digestSettings(), '/digest-settings', 'GET', undefined],
  [
    'save digest settings',
    () => api.saveDigestSettings({ channel: 'email', frequency: 'off', day: 'mon', alertThreshold: null, streams: null }),
    '/digest-settings',
    'PUT',
    { channel: 'email', frequency: 'off', day: 'mon', alertThreshold: null, streams: null },
  ],
  ['me', () => api.me(), '/me', 'GET', undefined],
  ['export', () => api.exportMe(), '/me/export', 'GET', undefined],
  ['delete account', () => api.deleteMe(), '/me', 'DELETE', undefined],
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
