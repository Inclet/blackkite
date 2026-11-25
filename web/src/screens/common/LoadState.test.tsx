import { fireEvent, render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import { ApiError } from '../../api/client';
import { COPY } from './copy';
import { LoadState } from './LoadState';

test('first load: the circling kite with the loading wording, never a spinner', () => {
  render(<LoadState loading />);
  expect(screen.getByTestId('kite-orbit')).toBeInTheDocument();
  expect(screen.getByRole('status')).toHaveTextContent(COPY.loadingTitle);
});

test('refreshing: the checking card says the list stays', () => {
  render(<LoadState refreshing />);
  expect(screen.getByText(COPY.refreshingTitle)).toBeInTheDocument();
  expect(screen.getByText(COPY.refreshingBody)).toBeInTheDocument();
});

test('an error: the source-down card with plain wording and Try again', () => {
  const retry = vi.fn();
  render(<LoadState error={new ApiError('unreachable', 500)} onRetry={retry} />);
  expect(screen.getByText(COPY.unreachableTitle)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: COPY.tryAgain }));
  expect(retry).toHaveBeenCalledOnce();
  expect(screen.queryByTestId('kite-orbit')).toBeNull();
});

test('nothing to say, or a 401 (the screen signs in instead): nothing', () => {
  const { container, rerender } = render(<LoadState />);
  expect(container).toBeEmptyDOMElement();
  rerender(<LoadState error={new ApiError('unauthorized', 401)} />);
  expect(container).toBeEmptyDOMElement();
});
