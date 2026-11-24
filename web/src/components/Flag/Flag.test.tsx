import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { Flag } from './Flag';

test('renders its text', () => {
  render(<Flag>Needs Umucyo account</Flag>);
  expect(screen.getByText('Needs Umucyo account')).toHaveClass('flag');
});

test('note variant is a block sentence', () => {
  render(<Flag variant="note">To check: this one may require an owned fleet.</Flag>);
  const el = screen.getByText(/To check:/);
  expect(el.tagName).toBe('DIV');
  expect(el).toHaveClass('note');
});
