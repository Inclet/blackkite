import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { referenceItems } from '../../fixtures/reference';
import { FILTER_COPY } from '../../lib/feedFilters';
import { setNowForTests } from '../../lib/now';
import { mockApi } from '../../test/mockApi';
import { renderAt, setViewport } from './testUtils';

beforeEach(() => {
  setNowForTests('2026-11-24T14:00:00+02:00');
  setViewport('desktop');
});
afterEach(() => {
  setNowForTests(null);
  vi.unstubAllGlobals();
});

const items = referenceItems().map((i) => ({ ...i, state: 'unseen', provisional: false }));
const FEED = { user: { name: 'Clet' }, sources: { checked: 3, when: 'today' }, digest: { channel: 'email' }, items };

function setup() {
  return mockApi({
    'GET /api/feed': (_b: unknown, url: string) => (url.includes('fit=strong') ? { ...FEED, items: items.filter((i) => i.fit === 'strong') } : FEED),
    'GET /api/shortlist': [],
    'GET /api/profiles': [{ id: 'p1', name: 'Ironji-Trade', type: 'business', data: { streams: ['tender'] }, version: 1, active: true }],
    'GET /api/sources': [{ id: 'src-jir', name: 'Job in Rwanda, tenders', homeUrl: 'https://x.rw', publisher: null, kind: 'publisher', streams: ['tender'], lastSuccessAt: null, items30d: 1, health: 'ok', muted: false }],
    'GET /me': { id: 'u', email: 'c@x.rw', name: 'Clet', role: 'member' },
  });
}
const feedUrls = (api: ReturnType<typeof mockApi>) => api.fetch.mock.calls.map(([u]) => u as string).filter((u) => u.startsWith('/api/feed'));

test('the panel applies each choice at once, in the URL and the API query; chips remove them; clear', async () => {
  const api = setup();
  const router = renderAt('/');
  const button = await screen.findByRole('button', { name: FILTER_COPY.button });
  expect(button).toHaveAttribute('aria-expanded', 'false');
  fireEvent.click(button);
  const panel = within(screen.getByRole('region', { name: FILTER_COPY.panel }));
  expect(panel.getAllByRole('group').map((g) => g.querySelector('legend')!.textContent)).toEqual(['Profile', 'Status', 'Deadline', 'Fit', 'Source', 'Trust']);
  // Fit in words only.
  const fit = within(panel.getAllByRole('group')[3]!);
  expect(fit.getAllByRole('button').map((b) => b.textContent)).toEqual(['Any', 'Strong', 'Good and up', 'Possible and up']);
  fireEvent.click(fit.getByRole('button', { name: 'Strong' }));
  fireEvent.click(panel.getByRole('button', { name: 'This week' }));
  fireEvent.click(panel.getByRole('button', { name: 'Ironji-Trade' }));
  fireEvent.click(await panel.findByRole('button', { name: 'Job in Rwanda, tenders' }));
  fireEvent.click(panel.getByRole('button', { name: 'Sources disagree' }));
  fireEvent.click(panel.getByRole('button', { name: 'Closing soon' }));
  expect(router.state.location.search).toBe('?fit=strong&window=7&profile=p1&source=src-jir&verification=conflict&status=closing_soon');
  await waitFor(() => expect(feedUrls(api).at(-1)).toBe('/api/feed?profile=p1&status=closing_soon&window=7&fit=strong&source=src-jir&verification=conflict'));
  expect(screen.getByRole('button', { name: 'Filters (6)' })).toBeInTheDocument();
  expect(fit.getByRole('button', { name: 'Strong' })).toHaveAttribute('aria-pressed', 'true');

  fireEvent.click(screen.getByRole('button', { name: FILTER_COPY.remove('Deadline', 'This week') }));
  expect(router.state.location.search).not.toContain('window');
  expect(screen.getByRole('button', { name: FILTER_COPY.remove('Profile', 'Ironji-Trade') })).toHaveTextContent('Profile: Ironji-Trade');
  fireEvent.click(screen.getAllByRole('button', { name: FILTER_COPY.clear })[0]!);
  expect(router.state.location.search).toBe('');
});

test('a filtered URL loads filtered, and keeps its filters when an item opens', async () => {
  const api = setup();
  const router = renderAt('/?fit=strong&window=bogus');
  await waitFor(() => expect(feedUrls(api)[0]).toBe('/api/feed?fit=strong'));
  const rows = await screen.findAllByRole('link', { name: /Logistics/ });
  expect(screen.getByRole('button', { name: FILTER_COPY.remove('Fit', 'Strong') })).toBeInTheDocument();
  fireEvent.click(rows[0]!);
  expect(router.state.location.pathname).toBe('/o/wfp-logistics');
  expect(router.state.location.search).toContain('fit=strong');
});

test('phone: the same tools under the chips', async () => {
  setViewport('phone');
  setup();
  renderAt('/?verification=confirmed');
  expect(await screen.findByRole('button', { name: 'Filters (1)' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: FILTER_COPY.remove('Trust', 'Confirmed at the source') })).toBeInTheDocument();
});

test('never on fixtures', () => {
  mockApi({});
  renderAt('/?fixture=reference&fit=strong');
  expect(screen.queryByRole('button', { name: /Filters/ })).toBeNull();
});
