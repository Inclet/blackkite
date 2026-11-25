import { fireEvent, render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import { SwitchRow } from './SwitchRow';

test('label, description and a switch named by the label and described by the description', () => {
  const onChange = vi.fn();
  render(<SwitchRow label="Urgent alerts" description="Email me the day a strong fit closes within 5 days." checked onChange={onChange} />);
  const sw = screen.getByRole('switch', { name: 'Urgent alerts' });
  expect(sw).toHaveAttribute('aria-checked', 'true');
  expect(sw).toHaveAccessibleDescription('Email me the day a strong fit closes within 5 days.');
  fireEvent.click(sw);
  expect(onChange).toHaveBeenCalledWith(false);
});

test('without a description there is nothing to describe it', () => {
  render(<SwitchRow label="Active" checked={false} onChange={() => {}} />);
  expect(screen.getByRole('switch', { name: 'Active' })).not.toHaveAttribute('aria-describedby');
});
