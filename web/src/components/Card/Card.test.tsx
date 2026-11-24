import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { Card } from './Card';

test('renders the label, padding and gap', () => {
  const { container } = render(
    <Card label="Buttons" padding="24px 28px" gap={16}>
      <p>content</p>
    </Card>,
  );
  const card = container.firstElementChild as HTMLElement;
  expect(card.style.padding).toBe('24px 28px');
  expect(card.style.gap).toBe('16px');
  expect(screen.getByText('Buttons')).toHaveClass('label');
  expect(screen.getByText('content')).toBeInTheDocument();
});

test('can render as an article with a label', () => {
  render(
    <Card as="article" aria-labelledby="h" padding="24px">
      <h2 id="h">Logistics</h2>
    </Card>,
  );
  expect(screen.getByRole('article', { name: 'Logistics' })).toHaveClass('card');
});
