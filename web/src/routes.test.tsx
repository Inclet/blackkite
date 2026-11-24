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
  ['/styleguide/foundations', 'Styleguide: foundations'],
  ['/styleguide/components', 'Styleguide: components'],
])('%s renders its screen', (url, name) => {
  renderAt(url);
  expect(screen.getByText(new RegExp(`^${name} \\(placeholder`))).toBeInTheDocument();
});

test('?fixture=reference selects the reference fixture', () => {
  renderAt('/?fixture=reference');
  expect(screen.getByText('Feed (placeholder, fixture: reference)')).toBeInTheDocument();
});

test('an unknown fixture falls back to live data', () => {
  renderAt('/?fixture=nope');
  expect(screen.getByText('Feed (placeholder)')).toBeInTheDocument();
});
