import { render } from '@testing-library/react';
import { expect, test } from 'vitest';
import { FitMeter } from './FitMeter';

test.each([
  ['strong', 3],
  ['good', 2],
  ['possible', 1],
] as const)('%s fills %i bars', (level, n) => {
  const { container } = render(<FitMeter level={level} />);
  const meter = container.firstElementChild!;
  expect(meter).toHaveAttribute('aria-hidden', 'true');
  const bars = meter.querySelectorAll<HTMLElement>('.bar');
  expect([...bars].map((b) => b.style.height)).toEqual(['6px', '10px', '14px']);
  expect(meter.querySelectorAll('.filled')).toHaveLength(n);
});
