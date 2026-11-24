import { render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { afterEach, beforeEach, expect, test } from 'vitest';
import { setNowForTests } from './lib/now';
import { routes } from './routes';

beforeEach(() => setNowForTests('2026-11-24T14:00:00+02:00'));
afterEach(() => setNowForTests(null));

function renderAt(url: string) {
  render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: [url] })} />);
}

test.each([
  ['/', 'Feed'],
  ['/o/wfp-logistics', 'Opportunity'],
  ['/digest/preview', 'Digest preview'],
])('%s without a fixture renders its placeholder (live data comes in Phase 4)', (url, name) => {
  renderAt(url);
  expect(screen.getByText(new RegExp(`^${name} \\(placeholder`))).toBeInTheDocument();
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

test.each(['/shortlist', '/calendar', '/sources', '/profiles', '/more'])('%s is a not-designed placeholder', (url) => {
  renderAt(url);
  expect(screen.getByText(/not designed yet/)).toBeInTheDocument();
});

test('an unknown fixture falls back to live data', () => {
  renderAt('/?fixture=nope');
  expect(screen.getByText('Feed (placeholder)')).toBeInTheDocument();
});
