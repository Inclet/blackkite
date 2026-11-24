import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { Kite, KITE_PATHS } from './Kite';

test('uses the path data from design/assets', () => {
  expect(KITE_PATHS.full).toMatch(/^M60,8 C63,8/);
  expect(KITE_PATHS.full).toContain('L112,34');
  expect(KITE_PATHS.small).not.toContain('L112,34');
});

test('is decorative without a label and an image with one', () => {
  const { container } = render(<Kite width={48} height={32} />);
  expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
  render(<Kite variant="full" width={180} height={120} label="Blackkite mark" />);
  expect(screen.getByRole('img', { name: 'Blackkite mark' })).toBeInTheDocument();
});

test('applies size, rotation and fill', () => {
  const { container } = render(<Kite width={26} height={17} rotate={-16} fill="#F6F5F2" />);
  const svg = container.querySelector('svg')!;
  expect(svg.style.width).toBe('26px');
  expect(svg.style.height).toBe('17px');
  expect(svg.style.transform).toBe('rotate(-16deg)');
  expect(svg.querySelector('path')).toHaveAttribute('fill', '#F6F5F2');
});
