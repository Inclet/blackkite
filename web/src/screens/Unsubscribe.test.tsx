import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { afterEach, expect, test, vi } from 'vitest';
import { routes } from '../routes';
import { UNSUBSCRIBE_COPY as C, unsubscribeTokenFrom } from './Unsubscribe';

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

const press = () => fireEvent.click(screen.getByRole('button', { name: C.button }));
const settingsLink = () => screen.getByRole('link', { name: C.settings });

test('nothing is sent on load; the token leaves the URL at once', async () => {
  const fetchMock = vi.fn();
  vi.stubGlobal('fetch', fetchMock);
  const router = renderAt('/unsubscribe#token=abc123');
  expect(screen.getByRole('heading', { level: 1, name: C.title })).toBeInTheDocument();
  await waitFor(() => expect(router.state.location.hash).toBe(''));
  expect(router.state.location.pathname).toBe('/unsubscribe');
  expect(router.state.location.search).toBe('');
  expect(router.state.historyAction).toBe('REPLACE');
  expect(screen.getByRole('button', { name: C.button })).toBeEnabled();
  expect(fetchMock).not.toHaveBeenCalled();
});

test('a digest token: posts {token} as JSON and says the emails have stopped', async () => {
  const fetchMock = vi.fn().mockResolvedValue(json(200, { kind: 'digest', detail: "You won't get these emails any more." }));
  vi.stubGlobal('fetch', fetchMock);
  renderAt('/unsubscribe#token=abc123');
  press();
  expect(await screen.findByText(C.doneDigest)).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(1);
  const [url, init] = fetchMock.mock.calls[0]!;
  expect(url).toBe('/api/unsubscribe');
  expect(init.method).toBe('POST');
  expect(init.redirect).toBe('manual');
  expect(init.headers['Content-Type']).toBe('application/json');
  expect(JSON.parse(init.body)).toEqual({ token: 'abc123' });
  expect(screen.queryByRole('button')).toBeNull();
  expect(settingsLink()).toHaveAttribute('href', '/settings/digest');
});

test('an alert token: says the alerts have stopped', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json(200, { kind: 'alert', detail: "You won't get these emails any more." })));
  renderAt('/unsubscribe#token=a');
  press();
  expect(await screen.findByText(C.doneAlert)).toBeInTheDocument();
  expect(settingsLink()).toBeInTheDocument();
});

test('400: the API’s own words, the settings link, and nothing left to press', async () => {
  const detail = 'This unsubscribe link is not valid. Change your emails in settings.';
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json(400, { detail })));
  renderAt('/unsubscribe#token=bad');
  press();
  expect(await screen.findByText(detail)).toBeInTheDocument();
  expect(screen.queryByRole('button')).toBeNull();
  expect(settingsLink()).toHaveAttribute('href', '/settings/digest');
});

test('400 without a detail falls back to the same wording', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json(400, {})));
  renderAt('/unsubscribe#token=bad');
  press();
  expect(await screen.findByText(C.invalid)).toBeInTheDocument();
});

test('429: too many tries, and the button stays', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json(429, { detail: 'Too many requests. Try again later.' })));
  renderAt('/unsubscribe#token=a');
  press();
  expect(await screen.findByText(C.tooMany)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: C.button })).toBeEnabled();
});

test.each([
  ['an opaque redirect', { ok: false, status: 0, type: 'opaqueredirect', json: () => Promise.reject(new Error()) }],
  ['a 303', { ok: false, status: 303, type: 'basic', json: () => Promise.reject(new Error()) }],
  ['a 200 without a kind', json(200, { detail: 'ok' })],
  ['a 200 that is not JSON', { ok: true, status: 200, type: 'basic', json: () => Promise.reject(new SyntaxError()) }],
  ['a 415', json(415, { detail: 'Send JSON {token} or the one-click form.' })],
  ['a 500', json(500, {})],
])('%s: could not reach Blackkite, try again', async (_name, response) => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response));
  renderAt('/unsubscribe#token=a');
  press();
  expect(await screen.findByText(C.unreachable)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: C.button })).toBeEnabled();
});

test('a network failure: could not reach Blackkite', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')));
  renderAt('/unsubscribe#token=x');
  press();
  expect(await screen.findByText(C.unreachable)).toBeInTheDocument();
});

test('no token: says so, offers the settings, and sends nothing', () => {
  const fetchMock = vi.fn();
  vi.stubGlobal('fetch', fetchMock);
  renderAt('/unsubscribe');
  expect(screen.queryByRole('button')).toBeNull();
  expect(screen.getByText(C.noToken)).toBeInTheDocument();
  expect(settingsLink()).toHaveAttribute('href', '/settings/digest');
  expect(fetchMock).not.toHaveBeenCalled();
});

test('a ?token= query is not read, and is removed from the URL', async () => {
  const router = renderAt('/unsubscribe?token=q');
  expect(screen.getByText(C.noToken)).toBeInTheDocument();
  await waitFor(() => expect(router.state.location.search).toBe(''));
});

test('the settings link moves within the app', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json(401, { detail: 'Sign in first.' })));
  const router = renderAt('/unsubscribe');
  fireEvent.click(settingsLink());
  await waitFor(() => expect(router.state.location.pathname).toBe('/settings/digest'));
});

test('the token is read from the fragment only', () => {
  expect(unsubscribeTokenFrom('#token=t1')).toBe('t1');
  expect(unsubscribeTokenFrom('')).toBe('');
  expect(unsubscribeTokenFrom('#other=1')).toBe('');
});

test('the page asks for no referrer', () => {
  renderAt('/unsubscribe#token=a');
  expect(document.head.querySelector('meta[name="referrer"]')).toHaveAttribute('content', 'no-referrer');
});
