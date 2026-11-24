import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { Flag } from './Flag';

test('renders its text', () => {
  render(<Flag>Needs Umucyo account</Flag>);
  expect(screen.getByText('Needs Umucyo account')).toHaveClass('flag');
});
