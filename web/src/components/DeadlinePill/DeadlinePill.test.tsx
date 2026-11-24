import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, test } from 'vitest';
import { setNowForTests } from '../../lib/now';
import { DeadlinePill } from './DeadlinePill';

beforeEach(() => setNowForTests('2026-11-24T14:00:00+02:00'));
afterEach(() => setNowForTests(null));

test.each([
  ['2026-12-26', '32 days left', 'quiet'],
  ['2026-12-06', '12 days left', 'outlined'],
  ['2026-11-30', '6 days left', 'solid'],
  ['2026-11-25', 'Closes tomorrow', 'alert'],
] as const)('%s reads "%s" (%s)', (deadline, text, weight) => {
  render(<DeadlinePill deadline={deadline} />);
  expect(screen.getByText(text)).toHaveClass('pill', weight);
});

test('plain-text variants', () => {
  render(
    <>
      <DeadlinePill deadline={null} />
      <DeadlinePill deadline={null} emptyText="No deadline" />
      <DeadlinePill deadline="2026-11-23" />
    </>,
  );
  expect(screen.getByText('No deadline stated')).toHaveClass('plain');
  expect(screen.getByText('No deadline')).toHaveClass('plain');
  expect(screen.getByText('Closed 23 Nov')).toHaveClass('plain');
});

test.each([
  ['2026-12-09', '2026-12-09', '9 Dec', 'quiet'], // 15 days
  ['2026-12-08', '2026-12-09', '8 to 9 Dec', 'outlined'], // 14 days
  ['2026-12-01', '2026-12-02', '1 to 2 Dec', 'outlined'], // 7 days: the boards' ABH Summit
  ['2026-11-30', null, '30 Nov', 'solid'], // 6 days
  ['2026-11-26', '2026-11-27', '26 to 27 Nov', 'solid'], // 2 days
  ['2026-11-25', '2026-11-25', '25 Nov', 'alert'], // the day before
  ['2026-11-24', '2026-11-24', '24 Nov', 'alert'], // the day of
  ['2026-11-23', '2026-11-25', '23 to 25 Nov', 'alert'], // under way
  ['2026-11-30', '2026-12-02', '30 Nov to 2 Dec', 'solid'],
] as const)('event %s to %s reads "%s" (%s)', (start, end, text, weight) => {
  render(<DeadlinePill event={{ start, end }} />);
  expect(screen.getByText(text)).toHaveClass('pill', weight);
});

test('an event that is over reads as plain text', () => {
  render(<DeadlinePill event={{ start: '2026-11-18', end: '2026-11-20' }} />);
  expect(screen.getByText('Ended 20 Nov')).toHaveClass('plain');
});

test('small size for phone rows', () => {
  render(
    <>
      <DeadlinePill deadline="2026-11-30" size="small" />
      <DeadlinePill event={{ start: '2026-12-01', end: '2026-12-02' }} size="small" />
      <DeadlinePill deadline={null} emptyText="No deadline" size="small" />
    </>,
  );
  expect(screen.getByText('6 days left')).toHaveClass('pill', 'solid', 'small');
  expect(screen.getByText('1 to 2 Dec')).toHaveClass('outlined', 'small');
  expect(screen.getByText('No deadline')).toHaveClass('plain', 'small');
});
