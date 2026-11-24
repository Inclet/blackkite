import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { afterEach, expect, test, vi } from 'vitest';
import { routes } from '../routes';

afterEach(() => vi.unstubAllGlobals());

function renderAt(url: string) {
  const router = createMemoryRouter(routes, { initialEntries: [url] });
  render(<RouterProvider router={router} />);
  return router;
}

test('posts the token and goes to the feed on success', async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 0, type: 'opaqueredirect' });
  vi.stubGlobal('fetch', fetchMock);
  const router = renderAt('/auth/confirm?token=abc123');
  expect(screen.getByRole('heading', { level: 1, name: 'Sign in to Blackkite' })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Continue to sign in' }));
  await waitFor(() => expect(router.state.location.pathname).toBe('/'));
  const [url, init] = fetchMock.mock.calls[0]!;
  expect(url).toBe('/auth/verify');
  expect(init.method).toBe('POST');
  expect(JSON.parse(init.body)).toEqual({ token: 'abc123' });
});

test('200 also counts as signed in', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200, type: 'basic' }));
  const router = renderAt('/auth/confirm?token=abc');
  fireEvent.click(screen.getByRole('button', { name: 'Continue to sign in' }));
  await waitFor(() => expect(router.state.location.pathname).toBe('/'));
});

test('an error shows a plain message and stays put', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 400, type: 'basic' }));
  const router = renderAt('/auth/confirm?token=spent');
  fireEvent.click(screen.getByRole('button', { name: 'Continue to sign in' }));
  expect(await screen.findByText(/expired or was already used/)).toBeInTheDocument();
  expect(router.state.location.pathname).toBe('/auth/confirm');
});

test('a network failure shows the same message', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')));
  renderAt('/auth/confirm?token=x');
  fireEvent.click(screen.getByRole('button', { name: 'Continue to sign in' }));
  expect(await screen.findByText(/expired or was already used/)).toBeInTheDocument();
});

test('without a token there is nothing to press', () => {
  renderAt('/auth/confirm');
  expect(screen.queryByRole('button')).toBeNull();
  expect(screen.getByText(/link is incomplete/)).toBeInTheDocument();
});
