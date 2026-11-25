import { fireEvent, render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import { FilterChip } from './FilterChip';

test('selected tender: pressed, icon in the text shade at 1.4', () => {
  render(<FilterChip stream="tender" selected />);
  const chip = screen.getByRole('button', { name: 'Tenders', pressed: true });
  expect(chip).toHaveClass('tender', 'selected');
  const svg = chip.querySelector('svg')!;
  expect(svg).toHaveAttribute('stroke', 'var(--bk-tender-text)');
  expect(svg).toHaveAttribute('stroke-width', '1.4');
});

test.each([
  ['tender', 'Tenders', 'var(--bk-tender-icon)'],
  ['investment', 'Investments', 'var(--bk-investment)'],
  ['funding', 'Funding', 'var(--bk-funding)'],
  ['event', 'Events', 'var(--bk-event)'],
] as const)('unselected %s: icon stroke %s at 1.6', (stream, name, stroke) => {
  render(<FilterChip stream={stream} selected={false} />);
  const chip = screen.getByRole('button', { name, pressed: false });
  expect(chip.querySelector('svg')).toHaveAttribute('stroke', stroke);
  expect(chip.querySelector('svg')).toHaveAttribute('stroke-width', '1.6');
});

test('All has no icon and reports clicks', () => {
  const onClick = vi.fn();
  render(<FilterChip stream="all" selected onClick={onClick} />);
  const chip = screen.getByRole('button', { name: 'All' });
  expect(chip.querySelector('svg')).toBeNull();
  fireEvent.click(chip);
  expect(onClick).toHaveBeenCalledOnce();
});

test('action: a plain one-shot button in the unselected look, no aria-pressed', () => {
  const onClick = vi.fn();
  render(<FilterChip stream="all" action label="Too small" onClick={onClick} />);
  const chip = screen.getByRole('button', { name: 'Too small' });
  expect(chip).not.toHaveAttribute('aria-pressed');
  expect(chip).toHaveAttribute('type', 'button');
  expect(chip).toHaveClass('chip', 'all', 'unselected');
  fireEvent.click(chip);
  expect(onClick).toHaveBeenCalledOnce();
});
