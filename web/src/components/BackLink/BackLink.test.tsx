import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { BackLink } from './BackLink';

test('a real link with a decorative back icon', () => {
  render(<BackLink href="/">Feed</BackLink>);
  const link = screen.getByRole('link', { name: 'Feed' });
  expect(link).toHaveAttribute('href', '/');
  expect(link.querySelector('[data-icon="back"]')).toHaveAttribute('aria-hidden', 'true');
});
