import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { AccountButton, accountInitial } from './AccountButton';

test('shows the initial and is named for what it does', () => {
  render(<AccountButton name="Clet" />);
  const b = screen.getByRole('button', { name: 'Your account' });
  expect(b).toHaveTextContent('C');
  expect(b).toHaveAttribute('type', 'button');
});

test('no name: the email\'s first letter; nothing at all: an empty button', () => {
  render(<AccountButton name="" email="clet@example.rw" />);
  expect(screen.getByRole('button', { name: 'Your account' })).toHaveTextContent(/^C$/);
  expect(accountInitial('  ', 'x@y.rw')).toBe('X');
  expect(accountInitial('', undefined)).toBe('');
  expect(accountInitial('amina', 'z@y.rw')).toBe('A');
});
