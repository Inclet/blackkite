import { useEffect, useRef } from 'react';

export interface FeedKeyHandlers {
  onNext: () => void;
  onPrevious: () => void;
  onSave: () => void;
  onDismiss: () => void;
}

/** Focus is somewhere typing happens: keys belong to it. */
function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  return target.closest('input, textarea, select, [contenteditable=""], [contenteditable="true"]') !== null;
}

/** J/K move, S saves, X marks not for me. Ignored with a modifier held or while typing. */
export function useFeedKeys(handlers: FeedKeyHandlers): void {
  const ref = useRef(handlers);
  ref.current = handlers;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey || e.isComposing) return;
      if (isTypingTarget(e.target)) return;
      const h = ref.current;
      const action = { j: h.onNext, k: h.onPrevious, s: h.onSave, x: h.onDismiss }[e.key.toLowerCase()];
      if (!action) return;
      e.preventDefault();
      action();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);
}
