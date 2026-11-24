import { render } from '@testing-library/react';
import { expect, test } from 'vitest';
import { Wordmark } from './Wordmark';

test('reads blackkite with the kk pair tightened', () => {
  const { container } = render(<Wordmark size={36} />);
  const root = container.firstElementChild as HTMLElement;
  expect(root).toHaveTextContent(/^blackkite$/);
  expect(root.style.fontSize).toBe('36px');
  expect(root.querySelector('.kk')).toHaveTextContent('kk');
});
