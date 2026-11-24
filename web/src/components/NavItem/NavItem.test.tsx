import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { NavItem } from './NavItem';

test('side items: the current one is aria-current page', () => {
  render(
    <nav aria-label="Main">
      <NavItem variant="side" href="/" current>
        Feed
      </NavItem>
      <NavItem variant="side" href="/shortlist">
        Shortlist
      </NavItem>
    </nav>,
  );
  expect(screen.getByRole('link', { name: 'Feed' })).toHaveAttribute('aria-current', 'page');
  expect(screen.getByRole('link', { name: 'Feed' })).toHaveClass('side', 'current');
  expect(screen.getByRole('link', { name: 'Shortlist' })).not.toHaveAttribute('aria-current');
});

test('tab items carry a decorative indicator', () => {
  render(
    <NavItem variant="tab" href="/" current>
      Feed
    </NavItem>,
  );
  const link = screen.getByRole('link', { name: 'Feed' });
  expect(link).toHaveClass('tab');
  expect(link.querySelector('[aria-hidden="true"]')).not.toBeNull();
});
