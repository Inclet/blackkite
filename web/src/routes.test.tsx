import { render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { expect, test } from 'vitest';
import { routes } from './routes';

function renderAt(url: string) {
  render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: [url] })} />);
}

test.each([
  ['/', 'Feed'],
  ['/o/wfp-logistics', 'Opportunity'],
  ['/digest/preview', 'Digest preview'],
])('%s renders its screen', (url, name) => {
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

test('?fixture=reference selects the reference fixture', () => {
  renderAt('/?fixture=reference');
  expect(screen.getByText('Feed (placeholder, fixture: reference)')).toBeInTheDocument();
});

test('an unknown fixture falls back to live data', () => {
  renderAt('/?fixture=nope');
  expect(screen.getByText('Feed (placeholder)')).toBeInTheDocument();
});
