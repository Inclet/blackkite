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

test('callers cannot override aria-invalid or aria-describedby', () => {
  render(<Field id="t" label="Trucks" error="Use a number." aria-invalid={false} aria-describedby="elsewhere" />);
  const input = screen.getByLabelText('Trucks');
  expect(input).toHaveAttribute('aria-invalid', 'true');
  expect(input).toHaveAttribute('aria-describedby', 't-error');
});

test('a hint sits under the input and is read with it, before any error', () => {
  render(<Field id="u" label="List page" hint="The page that lists the notices." error="Use the full address." />);
  const input = screen.getByLabelText('List page');
  expect(input).toHaveAttribute('aria-describedby', 'u-hint u-error');
  expect(input).toHaveAccessibleDescription('The page that lists the notices. Use the full address.');
  render(<Field id="v" label="Feed" hint="The feed address." />);
  expect(screen.getByLabelText('Feed')).toHaveAccessibleDescription('The feed address.');
  expect(screen.getByLabelText('Feed')).not.toHaveAttribute('aria-invalid');
});
