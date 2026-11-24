import { render } from '@testing-library/react';
import { expect, test } from 'vitest';
import { KiteOrbit, ORBITS } from './KiteOrbit';

test.each([
  ['signature', 150, 3, '14s'],
  ['checking', 72, 2, '6s'],
  ['feed', 28, 1, 'var(--bk-orbit)'],
] as const)('%s orbit: %ipx, %i rings, %s per circle', (name, size, rings, duration) => {
  const { getByTestId } = render(<KiteOrbit orbit={ORBITS[name]} />);
  const root = getByTestId('kite-orbit');
  expect(root.style.width).toBe(`${size}px`);
  expect(root.querySelectorAll('.ring')).toHaveLength(rings);
  expect((root.querySelector('.spin') as HTMLElement).style.animationDuration).toBe(duration);
  const kite = root.querySelector('svg')!;
  expect(kite.style.transform).toBe('rotate(90deg)');
  expect(kite.style.left).toBe(`${ORBITS[name].kite.left}px`);
});
