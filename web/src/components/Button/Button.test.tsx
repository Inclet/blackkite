import { fireEvent, render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import { Button } from './Button';

test('is a real button that defaults to type=button', () => {
  const onClick = vi.fn();
  render(<Button onClick={onClick}>Save to shortlist</Button>);
  const b = screen.getByRole('button', { name: 'Save to shortlist' });
  expect(b).toHaveAttribute('type', 'button');
  expect(b).toHaveClass('primary');
  fireEvent.click(b);
  expect(onClick).toHaveBeenCalledOnce();
});

test('secondary, disabled and forced states', () => {
  render(
    <>
      <Button variant="secondary">Not for me</Button>
      <Button disabled>Disabled</Button>
      <Button forceState="hover">Hover</Button>
      <Button forceState="focus">Keyboard focus</Button>
    </>,
  );
  expect(screen.getByRole('button', { name: 'Not for me' })).toHaveClass('secondary');
  expect(screen.getByRole('button', { name: 'Disabled' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Hover' })).toHaveClass('force-hover');
  expect(screen.getByRole('button', { name: 'Keyboard focus' })).toHaveClass('force-focus');
});
