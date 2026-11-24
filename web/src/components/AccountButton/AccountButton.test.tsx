import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { AccountButton } from './AccountButton';

test('shows the initial and is named for what it does', () => {
  render(<AccountButton name="Clet" />);
  const b = screen.getByRole('button', { name: 'Your account' });
  expect(b).toHaveTextContent('C');
  expect(b).toHaveAttribute('type', 'button');
});
