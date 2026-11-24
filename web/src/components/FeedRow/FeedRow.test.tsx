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

test('list layout: a link, selected with aria-current, no fit column', () => {
  render(
    <FeedRow
      layout="list"
      href="/o/wfp"
      selected
      stream="tender"
      title="Logistics, transport and warehousing support"
      subtitle="Strong fit · World Food Programme"
      fit="strong"
      deadline={{ deadline: '2026-11-30' }}
    />,
  );
  const link = screen.getByRole('link', { name: /Logistics, transport/ });
  expect(link).toHaveAttribute('href', '/o/wfp');
  expect(link).toHaveAttribute('aria-current', 'true');
  expect(link).toHaveClass('list', 'selected');
  expect(screen.queryByText('Strong')).toBeNull();
  expect(screen.getByText('6 days left')).not.toHaveClass('small');
});

test('phone layout: small pill, wrapped title, new rows drop in', () => {
  render(
    <FeedRow
      layout="phone"
      href="/o/abh"
      isNew
      stream="event"
      title="ABH Summit and Grand Finale"
      subtitle="Kigali Convention Centre"
      fit={null}
      deadline={{ event: { start: '2026-12-01', end: '2026-12-02' } }}
    />,
  );
  const link = screen.getByRole('link', { name: /ABH Summit/ });
  expect(link).toHaveClass('phone', 'new');
  expect(link).not.toHaveAttribute('aria-current');
  expect(screen.getByText('1 to 2 Dec')).toHaveClass('outlined', 'small');
});
