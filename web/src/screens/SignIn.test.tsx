import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { afterEach, expect, test, vi } from 'vitest';
import { routes } from '../routes';
import { SIGN_IN } from './SignIn';

afterEach(() => vi.unstubAllGlobals());

const reply = (status: number, body: unknown = {}) => new Response(JSON.stringify(body), { status });

function renderSignIn() {
  render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ['/sign-in'] })} />);
}

const type = (v: string) => fireEvent.change(screen.getByLabelText(SIGN_IN.label), { target: { value: v } });
const send = () => fireEvent.click(screen.getByRole('button', { name: SIGN_IN.button }));

test('posts the address to /auth/request-link and shows the plain confirmation', async () => {
  const fetchMock = vi.fn().mockResolvedValue(reply(202, { detail: 'If this address can sign in, a link is on its way.' }));
  vi.stubGlobal('fetch', fetchMock);
  renderSignIn();
  expect(screen.getByRole('heading', { level: 1, name: SIGN_IN.heading })).toBeInTheDocument();
  type('  clet@example.rw ');
  send();
  expect(await screen.findByText(SIGN_IN.sent)).toBeInTheDocument();
  const [url, init] = fetchMock.mock.calls[0]!;
  expect(url).toBe('/auth/request-link');
  expect(init.method).toBe('POST');
  expect(JSON.parse(init.body)).toEqual({ email: 'clet@example.rw' });
  expect(screen.queryByLabelText(SIGN_IN.label)).toBeNull();
});

test('pressing Enter in the field sends it too', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(202)));
  renderSignIn();
  type('clet@example.rw');
  fireEvent.submit(screen.getByLabelText(SIGN_IN.label).closest('form')!);
  expect(await screen.findByText(SIGN_IN.sent)).toBeInTheDocument();
});

test('an address that is not one gets the field error and nothing is sent', () => {
  const fetchMock = vi.fn();
  vi.stubGlobal('fetch', fetchMock);
  renderSignIn();
  type('clet');
  send();
  const input = screen.getByLabelText(SIGN_IN.label);
  expect(input).toHaveAttribute('aria-invalid', 'true');
  expect(input).toHaveAccessibleDescription(SIGN_IN.emailError);
  expect(fetchMock).not.toHaveBeenCalled();
});

test('the server refusing the address (422) is the same field error', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(422, { detail: [] })));
  renderSignIn();
  type('a@b.c');
  send();
  await waitFor(() => expect(screen.getByLabelText(SIGN_IN.label)).toHaveAttribute('aria-invalid', 'true'));
});

test.each([
  ['429', () => Promise.resolve(reply(429)), SIGN_IN.tooMany],
  ['500', () => Promise.resolve(reply(500)), SIGN_IN.unreachable],
  ['offline', () => Promise.reject(new TypeError('offline')), SIGN_IN.unreachable],
])('%s: a plain message, and the form stays', async (_n, impl, text) => {
  vi.stubGlobal('fetch', vi.fn().mockImplementation(impl));
  renderSignIn();
  type('clet@example.rw');
  send();
  expect(await screen.findByText(text)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: SIGN_IN.button })).toBeEnabled();
});
