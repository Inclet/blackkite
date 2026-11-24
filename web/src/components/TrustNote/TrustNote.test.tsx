import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { TrustNote } from './TrustNote';

test.each([
  ['confirmed', 'Confirmed at the source', '#2B2A28'],
  ['unconfirmed', 'Not yet confirmed at the source', '#5F5D59'],
  ['conflict', 'Sources disagree on the date', '#A12A21'],
] as const)('%s', (state, text, stroke) => {
  render(<TrustNote state={state} />);
  const note = screen.getByText(text);
  expect(note).toHaveClass(state);
  expect(note.querySelector('svg')).toHaveAttribute('stroke', stroke);
  expect(note.querySelector('svg')).toHaveAttribute('data-icon', state);
});
