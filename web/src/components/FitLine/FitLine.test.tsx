import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { FitLine } from './FitLine';

test('word and reason', () => {
  const { container } = render(<FitLine level="good" reason="matches, with something to check" />);
  expect(screen.getByText('Good').tagName).toBe('STRONG');
  expect(screen.getByText('matches, with something to check')).toBeInTheDocument();
  expect(container.querySelectorAll('.filled')).toHaveLength(2);
});

test('compact row form mutes Possible', () => {
  render(
    <>
      <FitLine level="strong" />
      <FitLine level="possible" />
    </>,
  );
  expect(screen.getByText('Strong')).not.toHaveClass('muted');
  expect(screen.getByText('Possible')).toHaveClass('compact', 'muted');
});
