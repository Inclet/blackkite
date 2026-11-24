import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { FitLine, FitReason } from './FitLine';

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

test('heading variant and reasons', () => {
  render(
    <>
      <FitLine level="strong" variant="heading" reason="why this matched" />
      <FitReason>It asks for transport.</FitReason>
    </>,
  );
  expect(screen.getByText('Strong fit · why this matched')).toHaveClass('heading');
  expect(screen.getByText('It asks for transport.').parentElement!.querySelector('[data-icon="check"]')).not.toBeNull();
});
