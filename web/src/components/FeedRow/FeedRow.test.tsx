import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, test } from 'vitest';
import { setNowForTests } from '../../lib/now';
import { FeedRow } from './FeedRow';

beforeEach(() => setNowForTests('2026-11-24T14:00:00+02:00'));
afterEach(() => setNowForTests(null));

test('scored row with a deadline', () => {
  render(
    <FeedRow
      stream="tender"
      title="Logistics, transport and warehousing support"
      subtitle="World Food Programme · matches your dry freight and cold chain"
      fit="strong"
      deadline={{ deadline: '2026-11-30' }}
    />,
  );
  expect(screen.getByRole('img', { name: 'Tender' })).toHaveAttribute('stroke', 'var(--bk-tender-text)');
  expect(screen.getByText('Strong')).toBeInTheDocument();
  expect(screen.getByText('6 days left')).toHaveClass('solid');
});

test('not scored, no deadline', () => {
  render(<FeedRow stream="investment" title="Five-year treasury bond" subtitle="National Bank of Rwanda" fit="not-scored" deadline={{ deadline: null }} />);
  expect(screen.getByText('Not scored')).toBeInTheDocument();
  expect(screen.getByText('No deadline stated')).toHaveClass('plain');
});

test('closed rows lose their colour', () => {
  const { container } = render(
    <FeedRow stream="tender" title="Invitation for bids" subtitle="AviaTech" fit={null} deadline={{ deadline: '2026-11-23' }} closed />,
  );
  expect(container.firstElementChild).toHaveClass('closed');
  expect(screen.getByRole('img', { name: 'Tender' })).toHaveAttribute('stroke', 'var(--bk-slate)');
  expect(screen.getByText('Closed 23 Nov')).toBeInTheDocument();
});
