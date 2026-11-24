import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { TrustNote, TrustPanel } from './TrustNote';

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

test.each(['mist', 'stone'] as const)('panel, %s tone', (tone) => {
  render(
    <TrustPanel state="unconfirmed" tone={tone}>
      Found on Job in Rwanda, posted 9 Nov.
    </TrustPanel>,
  );
  const body = screen.getByText('Found on Job in Rwanda, posted 9 Nov.');
  expect(body.parentElement).toHaveClass('panel', tone);
  expect(screen.getByText('Not yet confirmed at the source').querySelector('[data-icon="unconfirmed"]')).not.toBeNull();
});
