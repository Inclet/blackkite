import { useSyncExternalStore } from 'react';

/** Decision 6: the phone layout is used below 792 px. */
export const DESKTOP_QUERY = '(min-width: 792px)';

function query(): MediaQueryList | null {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function' ? window.matchMedia(DESKTOP_QUERY) : null;
}

function subscribe(onChange: () => void): () => void {
  const mq = query();
  if (!mq) return () => {};
  mq.addEventListener('change', onChange);
  return () => mq.removeEventListener('change', onChange);
}

/** True at 792 px and wider. Read synchronously on first render, so the right layout paints first (no layout shift). */
export function useIsDesktop(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => query()?.matches ?? true,
    () => true,
  );
}
