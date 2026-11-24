import { fireEvent, render, screen } from '@testing-library/react';
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
  expect(screen.getByText('6 days left')).toHaveClass('solid');
  expect(screen.getByText('13 days left')).toHaveClass('outlined');
  expect(screen.getByText('No deadline stated')).toBeInTheDocument();
  expect(screen.getByText('Closed 23 Nov')).toBeInTheDocument();
  expect(screen.getByLabelText('Refrigerated trucks')).toHaveAttribute('aria-invalid', 'true');
  const sw = screen.getByRole('switch', { name: 'Urgent alerts' });
  fireEvent.click(sw);
  expect(sw).toHaveAttribute('aria-checked', 'false');
  expect(screen.getByRole('button', { name: 'Tenders', pressed: true })).toBeInTheDocument();
});
