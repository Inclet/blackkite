import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import icons from '@design/assets/icons.json';
import { Icon } from './Icon';

test.each(Object.entries(icons.stream))('stream icon %s copies the path data', (name, d) => {
  const { container } = render(<Icon name={name as keyof typeof icons.stream} />);
  expect(container.querySelector('path')).toHaveAttribute('d', d);
});

test('size, stroke colour and stroke width', () => {
  const { container } = render(<Icon name="tender" size={15} stroke="#C98412" strokeWidth={1.6} />);
  const svg = container.querySelector('svg')!;
  expect(svg.style.width).toBe('15px');
  expect(svg).toHaveAttribute('stroke', '#C98412');
  expect(svg).toHaveAttribute('stroke-width', '1.6');
  expect(svg).toHaveAttribute('stroke-linecap', 'round');
  expect(svg).toHaveAttribute('aria-hidden', 'true');
});

test('trust icons', () => {
  const { container } = render(
    <>
      <Icon name="confirmed" />
      <Icon name="unconfirmed" />
      <Icon name="conflict" />
    </>,
  );
  const [confirmed, unconfirmed, conflict] = container.querySelectorAll('svg');
  expect(confirmed!.querySelector('circle')).toHaveAttribute('r', '6');
  expect(confirmed!.querySelector('path')).toHaveAttribute('d', icons.trust.confirmed.path);
  expect(unconfirmed!.querySelector('circle')).toHaveAttribute('stroke-dasharray', '2.2 2.2');
  expect(unconfirmed).not.toHaveAttribute('stroke-linecap');
  expect(conflict!.querySelector('path')).toHaveAttribute('d', icons.trust.conflict.path);
});

test('ui icons and labels', () => {
  render(<Icon name="clock" label="Clock" />);
  const svg = screen.getByRole('img', { name: 'Clock' });
  expect(svg.querySelector('circle')).toHaveAttribute('r', '6.25');
  expect(svg.querySelector('path')).toHaveAttribute('d', icons.ui.clock.path);
});
