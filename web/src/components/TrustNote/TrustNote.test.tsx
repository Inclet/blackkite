import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { TrustNote } from './TrustNote';

test.each([
  ['confirmed', 'Confirmed at the source', 'var(--bk-graphite)'],
  ['unconfirmed', 'Not yet confirmed at the source', 'var(--bk-slate)'],
  ['conflict', 'Sources disagree on the date', 'var(--bk-alert-text)'],
] as const)('%s', (state, text, stroke) => {
  render(<TrustNote state={state} />);
  const note = screen.getByText(text);
  expect(note).toHaveClass(state);
  expect(note.querySelector('svg')).toHaveAttribute('stroke', stroke);
  expect(note.querySelector('svg')).toHaveAttribute('data-icon', state);
});
