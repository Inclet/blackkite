import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { mockApi, status } from '../../test/mockApi';
import { renderAt, setViewport } from '../feed/testUtils';
import { SIGN_IN } from '../SignIn';
import { ACCOUNT_COPY } from './Account';
import { MORE_LINKS } from './More';

const ME = { id: 'u', email: 'clet@example.rw', name: 'Clet', role: 'admin' };

beforeEach(() => {
  setViewport('desktop');
  vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:x'), revokeObjectURL: vi.fn() }));
});
afterEach(() => vi.unstubAllGlobals());

const button = (name: string) => screen.getByRole('button', { name });

test('shows who is signed in', async () => {
  mockApi({ 'GET /me': ME });
  renderAt('/account');
  expect(await screen.findByText('clet@example.rw')).toBeInTheDocument();
  expect(within(screen.getByRole('navigation', { name: 'Main' })).getByRole('link', { name: 'Account' })).toHaveAttribute('aria-current', 'page');
});

test('export: GET /me/export becomes a download', async () => {
  const api = mockApi({ 'GET /me': ME, 'GET /me/export': { profiles: [] } });
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  renderAt('/account');
  await screen.findByText('clet@example.rw');
  fireEvent.click(button(ACCOUNT_COPY.export));
  expect(await screen.findByText(ACCOUNT_COPY.exported)).toBeInTheDocument();
  expect(api.calls.some((c) => c.key === 'GET /me/export')).toBe(true);
  expect(click).toHaveBeenCalledOnce();
  expect(URL.createObjectURL).toHaveBeenCalledOnce();
  click.mockRestore();
});

test('export that fails says so', async () => {
  mockApi({ 'GET /me': ME, 'GET /me/export': status(500) });
  renderAt('/account');
  await screen.findByText('clet@example.rw');
  fireEvent.click(button(ACCOUNT_COPY.export));
  expect(await screen.findByText(ACCOUNT_COPY.unreachable)).toBeInTheDocument();
});

test('delete: a confirm step that needs the email address, then DELETE /me and the sign-in screen', async () => {
  const api = mockApi({ 'GET /me': ME, 'DELETE /me': undefined });
  const router = renderAt('/account');
  await screen.findByText('clet@example.rw');
  fireEvent.click(button(ACCOUNT_COPY.delete));
  const confirmField = screen.getByLabelText(ACCOUNT_COPY.confirmField);
  fireEvent.click(button(ACCOUNT_COPY.confirm));
  expect(confirmField).toHaveAccessibleDescription(ACCOUNT_COPY.confirmError);
  expect(api.calls.some((c) => c.key === 'DELETE /me')).toBe(false);

  fireEvent.click(button(ACCOUNT_COPY.keep));
  expect(screen.queryByLabelText(ACCOUNT_COPY.confirmField)).toBeNull();
  fireEvent.click(button(ACCOUNT_COPY.delete));
  fireEvent.change(screen.getByLabelText(ACCOUNT_COPY.confirmField), { target: { value: ' Clet@Example.rw ' } });
  fireEvent.click(button(ACCOUNT_COPY.confirm));
  await waitFor(() => expect(router.state.location.pathname).toBe('/sign-in'));
  expect(api.calls.some((c) => c.key === 'DELETE /me')).toBe(true);
  expect(screen.getByText(ACCOUNT_COPY.deleted)).toBeInTheDocument();
  expect(button(SIGN_IN.button)).toBeInTheDocument();
});

test('a delete that fails keeps the account and says so', async () => {
  mockApi({ 'GET /me': ME, 'DELETE /me': status(503) });
  const router = renderAt('/account');
  await screen.findByText('clet@example.rw');
  fireEvent.click(button(ACCOUNT_COPY.delete));
  fireEvent.change(screen.getByLabelText(ACCOUNT_COPY.confirmField), { target: { value: 'clet@example.rw' } });
  fireEvent.click(button(ACCOUNT_COPY.confirm));
  expect(await screen.findByText(ACCOUNT_COPY.unreachable)).toBeInTheDocument();
  expect(router.state.location.pathname).toBe('/account');
});

test('sign out posts /auth/logout and goes to sign-in', async () => {
  const api = mockApi({ 'GET /me': ME, 'POST /auth/logout': undefined });
  const router = renderAt('/account');
  await screen.findByText('clet@example.rw');
  fireEvent.click(button(ACCOUNT_COPY.signOut));
  await waitFor(() => expect(router.state.location.pathname).toBe('/sign-in'));
  expect(api.calls.some((c) => c.key === 'POST /auth/logout')).toBe(true);
});

test('401 signs in', async () => {
  mockApi({ 'GET /me': status(401) });
  renderAt('/account');
  expect(await screen.findByRole('button', { name: SIGN_IN.button })).toBeInTheDocument();
});

test('More (phone): links to the screens the tab bar has no room for', async () => {
  setViewport('phone');
  mockApi({ 'GET /me': ME });
  const router = renderAt('/more');
  const card = within(screen.getByRole('region', { name: 'More' }));
  expect(card.getAllByRole('link').map((l) => [l.textContent, l.getAttribute('href')])).toEqual(MORE_LINKS.map((l) => [l.label, l.to]));
  expect(within(screen.getByRole('navigation', { name: 'Main' })).getByRole('link', { name: 'More' })).toHaveAttribute('aria-current', 'page');
  fireEvent.click(screen.getByRole('button', { name: 'Your account' }));
  expect(router.state.location.pathname).toBe('/account');
});
