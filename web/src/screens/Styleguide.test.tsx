import { fireEvent, render, screen, within } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { afterEach, beforeEach, expect, test } from 'vitest';
import { setNowForTests } from '../lib/now';
import { routes } from '../routes';

beforeEach(() => setNowForTests('2026-11-24T14:00:00+02:00'));
afterEach(() => setNowForTests(null));

function renderAt(url: string) {
  render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: [url] })} />);
}

test('foundations: urgency pills read as on the board at the frozen time', () => {
  renderAt('/styleguide/foundations?fixture=reference');
  for (const t of ['32 days left', '12 days left', '6 days left', 'Closes tomorrow']) expect(screen.getByText(t)).toBeInTheDocument();
  expect(screen.getByRole('img', { name: 'Blackkite mark' })).toBeInTheDocument();
  expect(screen.getByText('Mist').nextSibling).toHaveTextContent('#F6F5F2 · page');
  expect(screen.getByText('Marigold · #F2A83B · #FCEFD6 · #7A5200')).toBeInTheDocument();
});

test('components: feed rows, fields and the switch', () => {
  renderAt('/styleguide/components?fixture=reference');
  expect(within(screen.getByRole('main')).getByText('6 days left')).toHaveClass('solid');
  expect(within(screen.getByRole('main')).getByText('13 days left')).toHaveClass('outlined');
  expect(within(screen.getByRole('main')).getByText('No deadline stated')).toBeInTheDocument();
  expect(within(screen.getByRole('main')).getByText('Closed 23 Nov')).toBeInTheDocument();
  expect(screen.getByLabelText('Refrigerated trucks')).toHaveAttribute('aria-invalid', 'true');
  const sw = screen.getByRole('switch', { name: 'Urgent alerts' });
  fireEvent.click(sw);
  expect(sw).toHaveAttribute('aria-checked', 'false');
  expect(screen.getByRole('button', { name: 'Tenders', pressed: true })).toBeInTheDocument();
});

test('components: the Phase 2 screen variants sit below the board', () => {
  render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ['/styleguide/components?fixture=reference'] })} />);
  const variants = screen.getByRole('region', { name: 'Screen variants · below the board' });
  expect(within(variants).getAllByRole('link', { name: /Logistics, transport/ })[0]).toHaveAttribute('aria-current', 'true');
  expect(within(variants).getByRole('button', { name: 'Your account' })).toBeInTheDocument();
  expect(within(variants).getByText('1 to 2 Dec', { selector: '.small' })).toHaveClass('outlined');
  expect(screen.getByRole('main')).not.toContainElement(variants);
});
