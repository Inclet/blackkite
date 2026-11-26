import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from './client';

/**
 * The last good answer per key, for this page load. Coming back to a screen shows
 * it at once while the fresh copy loads ("checking" keeps the previous list on screen).
 */
const cache = new Map<string, unknown>();

export function clearApiCache(): void {
  cache.clear();
}

/** Read a cached value (to adjust it after a change made elsewhere). */
export function readCache<T>(key: string): T | undefined {
  return cache.get(key) as T | undefined;
}

/** Write a cached value (after an optimistic change, so a return visit starts from it). */
export function primeCache(key: string, value: unknown): void {
  cache.set(key, value);
}

export interface Resource<T> {
  data: T | undefined;
  /** The last failure; cleared by the next success. */
  error: ApiError | null;
  /** Nothing to show yet: the first load. */
  loading: boolean;
  /** Loading again with the previous data on screen. */
  refreshing: boolean;
  reload: () => void;
  /** Replace the data locally (optimistic updates); also updates the cache. */
  setData: (update: (prev: T | undefined) => T | undefined) => void;
}

function asApiError(e: unknown): ApiError {
  return e instanceof ApiError ? e : new ApiError('unreachable', 0);
}

/** Load `loader` once per mount (and on reload), keyed for the cache. Pass key null to skip. */
export function useResource<T>(key: string | null, loader: (signal: AbortSignal) => Promise<T>): Resource<T> {
  const [data, setDataState] = useState<T | undefined>(() => (key ? (cache.get(key) as T | undefined) : undefined));
  const [error, setError] = useState<ApiError | null>(null);
  const [pending, setPending] = useState(key !== null);
  const [attempt, setAttempt] = useState(0);
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  useEffect(() => {
    if (key === null) return;
    const ctl = new AbortController();
    setPending(true);
    loaderRef.current(ctl.signal).then(
      (value) => {
        if (ctl.signal.aborted) return;
        cache.set(key, value);
        setDataState(value);
        setError(null);
        setPending(false);
      },
      (e: unknown) => {
        if (ctl.signal.aborted) return;
        setError(asApiError(e));
        setPending(false);
      },
    );
    return () => ctl.abort();
  }, [key, attempt]);

  const setData = useCallback(
    (update: (prev: T | undefined) => T | undefined) => {
      setDataState((prev) => {
        const next = update(prev);
        if (key) cache.set(key, next);
        return next;
      });
    },
    [key],
  );

  return {
    data,
    error: pending ? null : error,
    loading: pending && data === undefined,
    refreshing: pending && data !== undefined,
    reload: useCallback(() => setAttempt((n) => n + 1), []),
    setData,
  };
}
