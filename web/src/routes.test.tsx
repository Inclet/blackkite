import { render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { mockApi } from './test/mockApi';
import { setNowForTests } from './lib/now';
import { routes } from './routes';

beforeEach(() => setNowForTests('2026-11-24T14:00:00+02:00'));
afterEach(() => {
  setNowForTests(null);
  vi.unstubAllGlobals();
});

function renderAt(url: string) {
  render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: [url] })} />);
}

test.each(['/', '/o/wfp-logistics'])('%s without a fixture loads from the API, with the circling kite meanwhile', (url) => {
  const api = mockApi({ 'GET /api/feed': () => new Promise(() => {}) });
  renderAt(url);
  expect(screen.getByTestId('kite-orbit')).toBeInTheDocument();
  expect(api.calls.map((c) => c.key)).toContain('GET /api/feed');
});

test('/digest/preview stays a placeholder (the harness serves the digest itself)', () => {
  renderAt('/digest/preview');
  expect(screen.getByText(/^Digest preview \(placeholder/)).toBeInTheDocument();
});

test.each([
  ['/styleguide/foundations?fixture=reference', 'Neutrals · everything structural'],
  ['/styleguide/components?fixture=reference', 'Feed row · built for scanning, and its awkward cases'],
])('%s renders its board', (url, text) => {
  renderAt(url);
  expect(screen.getByText(text)).toBeInTheDocument();
});

test('?fixture=reference renders the feed', () => {
  renderAt('/?fixture=reference');
  expect(screen.getByRole('heading', { level: 1, name: 'Good afternoon, Clet' })).toBeInTheDocument();
});

test('/calendar is the calendar, in the app frame with the feed board\'s sidebar', async () => {
  mockApi({ 'GET /me': { id: 'u', email: 'c@x.rw', name: 'Clet', role: 'admin' }, 'GET /api/calendar': { days: [] }, 'GET /api/calendar/feed-link': { url: 'https://x/c.ics?token=t' } });
  renderAt('/calendar');
  expect(screen.getByRole('heading', { level: 1, name: 'Calendar' })).toBeInTheDocument();
  expect(await screen.findByText('Nothing in November 2026 with these settings.')).toBeInTheDocument();
});

test('an unknown fixture falls back to live data', () => {
  const api = mockApi({ 'GET /api/feed': () => new Promise(() => {}) });
  renderAt('/?fixture=nope');
  expect(api.calls.map((c) => c.key)).toContain('GET /api/feed');
});
