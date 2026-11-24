import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { afterEach, expect, test, vi } from 'vitest';
import { routes } from '../routes';
import { MESSAGES, safeRedirect, tokenFrom } from './AuthConfirm';

afterEach(() => vi.unstubAllGlobals());

function renderAt(url: string) {
  const router = createMemoryRouter(routes, { initialEntries: [url] });
  render(<RouterProvider router={router} />);
  return router;
}

const json = (status: number, body: unknown) => ({
  ok: status >= 200 && status < 300,
  status,
  type: 'basic',
  json: () => Promise.resolve(body),
});

const press = () => fireEvent.click(screen.getByRole('button', { name: 'Continue to sign in' }));

test('reads the token from the fragment, cleans the URL, posts it and follows the redirect', async () => {
  const fetchMock = vi.fn().mockResolvedValue(json(200, { redirect: '/shortlist' }));
  vi.stubGlobal('fetch', fetchMock);
  const router = renderAt('/auth/confirm#token=abc123');
  expect(screen.getByRole('heading', { level: 1, name: 'Sign in to Blackkite' })).toBeInTheDocument();
  await waitFor(() => expect(router.state.location.hash).toBe(''));
  expect(router.state.location.pathname).toBe('/auth/confirm');
  expect(router.state.historyAction).toBe('REPLACE');
  press();
  await waitFor(() => expect(router.state.location.pathname).toBe('/shortlist'));
  const [url, init] = fetchMock.mock.calls[0]!;
  expect(url).toBe('/auth/verify');
  expect(init.method).toBe('POST');
  expect(init.redirect).toBe('manual');
  expect(JSON.parse(init.body)).toEqual({ token: 'abc123' });
});

test('old ?token= links still work, and the query is removed too', async () => {
  const fetchMock = vi.fn().mockResolvedValue(json(200, { redirect: '/' }));
  vi.stubGlobal('fetch', fetchMock);
  const router = renderAt('/auth/confirm?token=old');
  await waitFor(() => expect(router.state.location.search).toBe(''));
  press();
  await waitFor(() => expect(router.state.location.pathname).toBe('/'));
  expect(JSON.parse(fetchMock.mock.calls[0]![1].body)).toEqual({ token: 'old' });
});

test('the fragment wins over the query', () => {
  expect(tokenFrom({ hash: '#token=new', search: '?token=old' })).toBe('new');
  expect(tokenFrom({ hash: '', search: '?token=old' })).toBe('old');
  expect(tokenFrom({ hash: '', search: '' })).toBe('');
});

test('a redirect off this origin goes to the feed instead', () => {
  const o = 'https://app.test';
  expect(safeRedirect('/o/x?y=1', o)).toBe('/o/x?y=1');
  expect(safeRedirect('https://evil.test/', o)).toBe('/');
  expect(safeRedirect('//evil.test/', o)).toBe('/');
  expect(safeRedirect('/\\evil.test', o)).toBe('/');
  expect(safeRedirect('javascript:alert(1)', o)).toBe('/');
  expect(safeRedirect(42, o)).toBe('/');
});

test('an absolute redirect from the API is replaced by /', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json(200, { redirect: 'https://evil.test/' })));
  const router = renderAt('/auth/confirm#token=a');
  press();
  await waitFor(() => expect(router.state.location.pathname).toBe('/'));
});

test.each([
  ['an opaque redirect', { ok: false, status: 0, type: 'opaqueredirect', json: () => Promise.reject(new Error()) }],
  ['a 303', { ok: false, status: 303, type: 'basic', json: () => Promise.reject(new Error()) }],
  ['a 200 without {redirect}', json(200, { ok: true })],
  ['a 200 that is not JSON', { ok: true, status: 200, type: 'basic', json: () => Promise.reject(new SyntaxError()) }],
  ['a 500', json(500, {})],
])('%s is not a sign-in', async (_name, response) => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response));
  const router = renderAt('/auth/confirm#token=a');
  press();
  expect(await screen.findByText(MESSAGES.unreachable)).toBeInTheDocument();
  expect(router.state.location.pathname).toBe('/auth/confirm');
});

test('400: expired or used, and nothing left to press', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json(400, { detail: 'invalid' })));
  renderAt('/auth/confirm#token=spent');
  press();
  expect(await screen.findByText(MESSAGES.invalid)).toBeInTheDocument();
  expect(screen.queryByRole('button')).toBeNull();
});

test('429: too many tries', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json(429, {})));
  renderAt('/auth/confirm#token=a');
  press();
  expect(await screen.findByText(MESSAGES.tooMany)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Continue to sign in' })).toBeEnabled();
});

test('a network failure: could not reach the server', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')));
  renderAt('/auth/confirm#token=x');
  press();
  expect(await screen.findByText(MESSAGES.unreachable)).toBeInTheDocument();
});

test('without a token there is nothing to press and nothing is sent', () => {
  const fetchMock = vi.fn();
  vi.stubGlobal('fetch', fetchMock);
  renderAt('/auth/confirm');
  expect(screen.queryByRole('button')).toBeNull();
  expect(screen.getByText(MESSAGES.noToken)).toBeInTheDocument();
  expect(fetchMock).not.toHaveBeenCalled();
});

test('the page asks for no referrer', () => {
  renderAt('/auth/confirm#token=a');
  expect(document.head.querySelector('meta[name="referrer"]')).toHaveAttribute('content', 'no-referrer');
});
