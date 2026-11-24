import { fireEvent, render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import { Switch } from './Switch';

test('is a switch that reports the next state', () => {
  const onChange = vi.fn();
  render(<Switch checked label="Urgent alerts" onChange={onChange} />);
  const sw = screen.getByRole('switch', { name: 'Urgent alerts' });
  expect(sw).toHaveAttribute('aria-checked', 'true');
  expect(sw).toHaveClass('on');
  fireEvent.click(sw);
  expect(onChange).toHaveBeenCalledWith(false);
});

test('off state', () => {
  render(<Switch checked={false} label="Urgent alerts" />);
  expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false');
});
