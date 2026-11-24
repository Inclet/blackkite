import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { TextLink } from './TextLink';

test('renders a real link with its spacing', () => {
  render(
    <>
      <TextLink href="/original">Read the original</TextLink>
      <TextLink href="/shortlist" spacing="stacked">Open shortlist</TextLink>
    </>,
  );
  expect(screen.getByRole('link', { name: 'Read the original' })).toHaveClass('link', 'inline');
  expect(screen.getByRole('link', { name: 'Open shortlist' })).toHaveAttribute('href', '/shortlist');
  expect(screen.getByRole('link', { name: 'Open shortlist' })).toHaveClass('stacked');
});
