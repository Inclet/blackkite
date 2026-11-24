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

test('events take an explicit weight', () => {
  render(<DeadlinePill weight="outlined" label="In 9 days" />);
  expect(screen.getByText('In 9 days')).toHaveClass('outlined');
});
