import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { setNowForTests } from '../../lib/now';
import { mockApi, status } from '../../test/mockApi';
import { renderAt, setViewport } from '../feed/testUtils';
import { SIGN_IN } from '../SignIn';
import { CALENDAR_COPY, entryLabel } from './Calendar';
import { FEED_LINK_COPY } from './FeedLinkCard';

beforeEach(() => {
  setNowForTests('2026-11-24T14:00:00+02:00');
  setViewport('desktop');
});
afterEach(() => {
  setNowForTests(null);
  vi.unstubAllGlobals();
});

const ME = { id: 'u', email: 'c@x.rw', name: 'Clet', role: 'member' };
const DAYS = {
  days: [
    { date: '2026-11-24', entries: [{ id: 'today-call', stream: 'funding', title: 'Closing today call', kind: 'deadline', fit: 'good', state: 'unseen', provisional: false }] },
    { date: '2026-11-30', entries: [{ id: 'wfp-logistics', stream: 'tender', title: 'Logistics support', organisationShort: 'WFP', kind: 'deadline', time: '17:00', fit: 'strong', state: 'saved', provisional: false }] },
    { date: '2026-12-01', entries: [] },
  ],
};
const LINK = { url: 'https://blackkite.example/api/calendar.ics?token=v1' };

function setup(days: unknown = DAYS) {
  return mockApi({ 'GET /me': ME, 'GET /api/calendar': days, 'GET /api/calendar/feed-link': LINK, 'POST /api/calendar/feed-link/rotate': { url: 'https://blackkite.example/api/calendar.ics?token=v2' } });
}
const calendarUrls = (api: ReturnType<typeof mockApi>) => api.fetch.mock.calls.map(([u]) => u as string).filter((u) => u.startsWith('/api/calendar?'));

test('labels: Closes with the time, past tense once passed', () => {
  const e = { id: 'x', stream: 'tender', title: 'x', kind: 'deadline', time: '17:00', state: 'unseen', provisional: false } as const;
  expect(entryLabel(e, '2026-11-30')).toBe('Closes 5pm');
  expect(entryLabel({ ...e, time: undefined }, '2026-11-01')).toBe('Closed');
  expect(entryLabel({ ...e, kind: 'event_start', time: undefined }, '2026-12-01')).toBe('Starts');
  expect(entryLabel({ ...e, kind: 'event', time: undefined }, '2026-12-01')).toBe('Event');
});

test('desktop: a month grid for this month, today marked, entries open the item', async () => {
  const api = setup();
  const router = renderAt('/calendar');
  const grid = await screen.findByRole('table', { name: 'November 2026' });
  expect(calendarUrls(api)[0]).toBe('/api/calendar?from=2026-11-01&to=2026-11-30&kind=all');
  expect(within(grid).getAllByRole('columnheader').map((h) => h.textContent)).toEqual(['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']);
  const today = grid.querySelector('[aria-current="date"]')!;
  expect(today).toHaveTextContent('Today, Tuesday 24 November 2026');
  const wfp = within(grid).getByRole('link', { name: /Logistics support/ });
  expect(wfp).toHaveTextContent('Closes 5pm');
  expect(wfp).toHaveTextContent('Strong');
  expect(wfp).toHaveAttribute('href', '/o/wfp-logistics');
  // Deadline weights: 6 days left is solid.
  expect(within(wfp).getByText('Closes 5pm').className).toMatch(/solid/);
  expect(within(grid).getByText('Closing today call').closest('a')!.querySelector('[class*="alert"]')).not.toBeNull();
  fireEvent.click(wfp);
  expect(router.state.location.pathname).toBe('/o/wfp-logistics');
});

test('arrow keys move between days with entries', async () => {
  setup();
  renderAt('/calendar');
  const grid = await screen.findByRole('table');
  const first = within(grid).getByRole('link', { name: /Closing today call/ });
  first.focus();
  fireEvent.keyDown(first, { key: 'ArrowRight' });
  expect(within(grid).getByRole('link', { name: /Logistics support/ })).toHaveFocus();
  // Up a week from 30 Nov is 23 Nov and earlier: nothing there, so focus stays.
  fireEvent.keyDown(document.activeElement!, { key: 'ArrowUp' });
  expect(within(grid).getByRole('link', { name: /Logistics support/ })).toHaveFocus();
  fireEvent.keyDown(document.activeElement!, { key: 'ArrowLeft' });
  expect(first).toHaveFocus();
  fireEvent.keyDown(first, { key: 'ArrowLeft' });
  expect(first).toHaveFocus();
});

test('the list view is the same dates as a real list, by day', async () => {
  setup();
  renderAt('/calendar?view=list');
  const list = await screen.findByRole('list', { name: 'Days' });
  expect(screen.queryByRole('table')).toBeNull();
  const days = within(list).getAllByRole('heading', { level: 3 }).map((h) => h.textContent);
  expect(days).toEqual(['Tuesday 24 November 2026Today', 'Monday 30 November 2026']);
  expect(within(list).getByRole('link', { name: /Logistics support/ })).toHaveTextContent('WFP');
});

test('phone: always the list, no view switch', async () => {
  setViewport('phone');
  setup();
  renderAt('/calendar');
  await screen.findByRole('list', { name: 'Days' });
  expect(screen.queryByRole('group', { name: CALENDAR_COPY.view })).toBeNull();
});

test('show, saved only and months go in the URL and the query', async () => {
  const api = setup({ days: [] });
  const router = renderAt('/calendar');
  await screen.findByText('Nothing in November 2026 with these settings.');
  fireEvent.click(screen.getByRole('button', { name: 'Deadlines' }));
  fireEvent.click(screen.getByRole('button', { name: CALENDAR_COPY.savedOnly }));
  fireEvent.click(screen.getByRole('button', { name: CALENDAR_COPY.next }));
  await screen.findByText('Nothing in December 2026 with these settings.');
  expect(router.state.location.search).toBe('?show=deadlines&saved=1&month=2026-12');
  expect(calendarUrls(api).at(-1)).toBe('/api/calendar?from=2026-12-01&to=2026-12-31&kind=deadlines&saved=true');
  expect(screen.getByRole('button', { name: 'Deadlines' })).toHaveAttribute('aria-pressed', 'true');
  fireEvent.click(screen.getByRole('button', { name: CALENDAR_COPY.thisMonth }));
  await screen.findByText('Nothing in November 2026 with these settings.');
  expect(screen.queryByRole('button', { name: CALENDAR_COPY.thisMonth })).toBeNull();
});

test('feed link: copy, and stop with a confirm', async () => {
  const writeText = vi.fn(async () => {});
  vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } });
  const api = setup();
  renderAt('/calendar');
  const card = within(await screen.findByRole('region', { name: FEED_LINK_COPY.title }));
  expect(card.getByText(/never shows your notes, scores or profiles/)).toBeInTheDocument();
  expect(await card.findByLabelText(FEED_LINK_COPY.label)).toHaveValue(LINK.url);
  fireEvent.click(card.getByRole('button', { name: FEED_LINK_COPY.copy }));
  await card.findByText(FEED_LINK_COPY.copied);
  expect(writeText).toHaveBeenCalledWith(LINK.url);

  const stop = card.getByRole('button', { name: FEED_LINK_COPY.stop });
  fireEvent.click(stop);
  expect(stop).toHaveAttribute('aria-expanded', 'true');
  fireEvent.click(card.getByRole('button', { name: FEED_LINK_COPY.confirmNo }));
  expect(api.calls.some((c) => c.key === 'POST /api/calendar/feed-link/rotate')).toBe(false);
  fireEvent.click(stop);
  fireEvent.click(card.getByRole('button', { name: FEED_LINK_COPY.confirmYes }));
  await card.findByText(FEED_LINK_COPY.stopped);
  expect(card.getByLabelText(FEED_LINK_COPY.label)).toHaveValue('https://blackkite.example/api/calendar.ics?token=v2');
});

test('feed link: a failed copy says how to do it by hand; a failed stop keeps the link', async () => {
  vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText: async () => Promise.reject(new Error('no')) } });
  const api = setup();
  renderAt('/calendar');
  const card = within(await screen.findByRole('region', { name: FEED_LINK_COPY.title }));
  await card.findByLabelText(FEED_LINK_COPY.label);
  fireEvent.click(card.getByRole('button', { name: FEED_LINK_COPY.copy }));
  await card.findByText(FEED_LINK_COPY.copyFailed);
  api.on('POST /api/calendar/feed-link/rotate', status(500));
  fireEvent.click(card.getByRole('button', { name: FEED_LINK_COPY.stop }));
  fireEvent.click(card.getByRole('button', { name: FEED_LINK_COPY.confirmYes }));
  await card.findByText(FEED_LINK_COPY.stopFailed);
  expect(card.getByLabelText(FEED_LINK_COPY.label)).toHaveValue(LINK.url);
});

test('401 signs in', async () => {
  mockApi({ 'GET /api/calendar': status(401), 'GET /api/calendar/feed-link': status(401) });
  renderAt('/calendar');
  expect(await screen.findByRole('button', { name: SIGN_IN.button })).toBeInTheDocument();
});

test('nav: Calendar is current', async () => {
  setup();
  renderAt('/calendar');
  await waitFor(() => expect(screen.getByRole('link', { name: 'Calendar' })).toHaveAttribute('aria-current', 'page'));
});
