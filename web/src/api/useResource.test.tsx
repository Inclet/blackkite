import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import { ApiError } from './client';
import { clearApiCache, useResource } from './useResource';

afterEach(() => clearApiCache());

test('first load: loading, then data', async () => {
  const loader = vi.fn().mockResolvedValue(['a']);
  const { result } = renderHook(() => useResource('k', loader));
  expect(result.current).toMatchObject({ loading: true, refreshing: false, data: undefined });
  await waitFor(() => expect(result.current.data).toEqual(['a']));
  expect(result.current).toMatchObject({ loading: false, refreshing: false, error: null });
});

test('a second mount shows the cached data while it refreshes', async () => {
  const first = renderHook(() => useResource('k', () => Promise.resolve(['old'])));
  await waitFor(() => expect(first.result.current.data).toEqual(['old']));
  first.unmount();
  let resolve!: (v: string[]) => void;
  const second = renderHook(() => useResource('k', () => new Promise<string[]>((r) => (resolve = r))));
  expect(second.result.current).toMatchObject({ data: ['old'], loading: false, refreshing: true });
  await act(async () => resolve(['new']));
  expect(second.result.current).toMatchObject({ data: ['new'], refreshing: false });
});

test('a failure keeps the previous data and reports the error; reload tries again', async () => {
  const loader = vi.fn().mockResolvedValueOnce(['a']).mockRejectedValueOnce(new ApiError('unreachable', 500)).mockResolvedValueOnce(['b']);
  const { result } = renderHook(() => useResource('k', loader));
  await waitFor(() => expect(result.current.data).toEqual(['a']));
  act(() => result.current.reload());
  await waitFor(() => expect(result.current.error?.kind).toBe('unreachable'));
  expect(result.current.data).toEqual(['a']);
  act(() => result.current.reload());
  await waitFor(() => expect(result.current.data).toEqual(['b']));
  expect(result.current.error).toBeNull();
});

test('anything thrown that is not an ApiError counts as unreachable', async () => {
  const { result } = renderHook(() => useResource('k', () => Promise.reject(new Error('boom'))));
  await waitFor(() => expect(result.current.error).toBeInstanceOf(ApiError));
  expect(result.current.error?.kind).toBe('unreachable');
});

test('setData changes the data and the cache', async () => {
  const { result, unmount } = renderHook(() => useResource('k', () => Promise.resolve([1])));
  await waitFor(() => expect(result.current.data).toEqual([1]));
  act(() => result.current.setData((p) => [...(p ?? []), 2]));
  expect(result.current.data).toEqual([1, 2]);
  unmount();
  const again = renderHook(() => useResource('k', () => new Promise<number[]>(() => {})));
  expect(again.result.current.data).toEqual([1, 2]);
});

test('key null loads nothing', () => {
  const loader = vi.fn();
  const { result } = renderHook(() => useResource(null, loader));
  expect(loader).not.toHaveBeenCalled();
  expect(result.current).toMatchObject({ loading: false, refreshing: false });
});
