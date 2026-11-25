import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { referenceItems } from '../../fixtures/reference';
import { setNowForTests } from '../../lib/now';
import { mockApi, status } from '../../test/mockApi';
import { COPY } from '../common/copy';
import { renderAt, setViewport } from '../feed/testUtils';
import { SIGN_IN } from '../SignIn';
import { SHORTLIST_COPY } from './Shortlist';

beforeEach(() => {
  setNowForTests('2026-11-24T14:00:00+02:00');
  setViewport('desktop');
});
afterEach(() => {
  setNowForTests(null);
  vi.unstubAllGlobals();
});

const ME = { id: 'u', email: 'c@x.rw', name: 'Clet', role: 'member' };

test('saved and acting items, closing soonest first, in feed rows that open the item', async () => {
  const [wfp, abh, , , , bond] = referenceItems();
  mockApi({ 'GET /api/shortlist': [{ ...bond!, state: 'saved' }, { ...wfp!, state: 'acting' }, { ...abh!, state: 'saved' }], 'GET /me': ME });
  const router = renderAt('/shortlist');
  expect(screen.getByTestId('kite-orbit')).toBeInTheDocument();
  const list = within(await screen.findByRole('region', { name: 'Shortlist' }));
  const rows = list.getAllByRole('link');
  expect(rows.map((r) => r.getAttribute('href'))).toEqual(['/o/wfp-logistics', '/o/abh-summit', `/o/${bond!.id}`]);
  expect(screen.getByRole('heading', { level: 1, name: 'Shortlist' })).toBeInTheDocument();
  expect(screen.getByText('3 items saved or in progress, closing soonest first.')).toBeInTheDocument();
  const nav = screen.getByRole('navigation', { name: 'Main' });
  expect(within(nav).getByRole('link', { name: 'Shortlist' })).toHaveAttribute('aria-current', 'page');
  fireEvent.click(rows[0]!);
  expect(router.state.location.pathname).toBe('/o/wfp-logistics');
});

test('phone: the phone rows and the tab bar', async () => {
  setViewport('phone');
  mockApi({ 'GET /api/shortlist': [referenceItems()[0]], 'GET /me': ME });
  renderAt('/shortlist');
  await screen.findByRole('region', { name: 'Shortlist' });
  const tabs = screen.getByRole('navigation', { name: 'Main' });
  expect(within(tabs).getAllByRole('link').map((l) => l.textContent)).toEqual(['Feed', 'Shortlist', 'Calendar', 'More']);
  expect(within(tabs).getByRole('link', { name: 'Shortlist' })).toHaveAttribute('aria-current', 'page');
  await waitFor(() => expect(screen.getByRole('button', { name: 'Your account' })).toHaveTextContent('C'));
});

test('empty: the nothing-new card pointing at the feed', async () => {
  mockApi({ 'GET /api/shortlist': [], 'GET /me': ME });
  const router = renderAt('/shortlist');
  expect(await screen.findByText(SHORTLIST_COPY.emptyTitle)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: SHORTLIST_COPY.openFeed }));
  expect(router.state.location.pathname).toBe('/');
});

test('401 signs in; unreachable says so', async () => {
  mockApi({ 'GET /api/shortlist': status(401) });
  renderAt('/shortlist');
  expect(await screen.findByRole('button', { name: SIGN_IN.button })).toBeInTheDocument();
});

test('unreachable: plain wording and Try again', async () => {
  const api = mockApi({ 'GET /api/shortlist': status(500), 'GET /me': ME });
  renderAt('/shortlist');
  expect(await screen.findByText(COPY.unreachableTitle)).toBeInTheDocument();
  api.on('GET /api/shortlist', []);
  fireEvent.click(screen.getByRole('button', { name: COPY.tryAgain }));
  expect(await screen.findByText(SHORTLIST_COPY.emptyTitle)).toBeInTheDocument();
});
