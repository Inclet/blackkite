import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { Tag } from './Tag';

test('stream tag defaults to the stream name', () => {
  render(<Tag kind="stream" stream="investment" />);
  expect(screen.getByText('Investment')).toHaveClass('tag', 'investment');
});

test('icon and evening variants', () => {
  render(
    <Tag kind="stream" stream="tender" icon evening>
      Evening
    </Tag>,
  );
  const tag = screen.getByText('Evening');
  expect(tag).toHaveAttribute('data-theme', 'evening');
  expect(tag.querySelector('svg')).toHaveAttribute('stroke', 'currentColor');
});

test('profile tag is neutral', () => {
  render(<Tag kind="profile">Ironji-Trade</Tag>);
  expect(screen.getByText('Ironji-Trade')).toHaveClass('profile');
});
