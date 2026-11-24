import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { StateCard } from './StateCard';

test('checking shows the circling kite as a status', () => {
  render(<StateCard kind="checking" title="Checking 8 sources" body="Usually under a minute." />);
  expect(screen.getByRole('status')).toHaveTextContent('Checking 8 sources');
  expect(screen.getByTestId('kite-orbit').style.width).toBe('72px');
});

test('nothing new links on', () => {
  render(<StateCard kind="nothing-new" title="Nothing new since yesterday" body="All 8 sources were checked." action={{ label: 'Open shortlist', href: '/shortlist' }} />);
  expect(screen.getByRole('link', { name: 'Open shortlist' })).toHaveAttribute('href', '/shortlist');
});

test('first visit offers a button', () => {
  render(<StateCard kind="first-visit" title="Tell Blackkite what you do" body="Three questions." action={{ label: 'Set up a profile' }} />);
  expect(screen.getByRole('button', { name: 'Set up a profile' })).toHaveClass('primary');
});

test('source down leads with the conflict icon', () => {
  render(<StateCard kind="source-down" title="We could not reach BNR today" body="Bond notices may be a day behind." action={{ label: 'See all sources' }} />);
  expect(screen.getByText('We could not reach BNR today').querySelector('[data-icon="conflict"]')).not.toBeNull();
});
