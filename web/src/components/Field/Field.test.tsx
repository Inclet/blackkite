import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { Field } from './Field';

test('label is tied to the input', () => {
  render(<Field label="Smallest contract worth bidding" defaultValue="FRW 5,000,000" />);
  const input = screen.getByLabelText('Smallest contract worth bidding');
  expect(input).toHaveValue('FRW 5,000,000');
  expect(input).not.toHaveAttribute('aria-invalid');
  expect(input).not.toHaveAttribute('aria-describedby');
});

test('an error marks the input invalid and describes it', () => {
  render(<Field id="trucks" label="Refrigerated trucks" defaultValue="about a hundred" error="Use a number, such as 100." />);
  const input = screen.getByLabelText('Refrigerated trucks');
  expect(input).toHaveAttribute('aria-invalid', 'true');
  expect(input).toHaveAttribute('aria-describedby', 'trucks-error');
  expect(input).toHaveAccessibleDescription('Use a number, such as 100.');
});
