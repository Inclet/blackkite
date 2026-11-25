import { useLayoutEffect, useRef } from 'react';
import type { FeedItem } from '../../fixtures/types';

/**
 * The list as the keys last left it. A dismissal only reaches the rendered list
 * after React re-renders, so a second key in the same tick would still see the
 * removed row. `dismiss` records the id here synchronously. Once a render has
 * left the row out, a later render that shows it again (a dismissal undone
 * because the server could not be reached) brings it back for the keys too.
 */
export function useLiveList(rendered: FeedItem[]) {
  const latest = useRef(rendered);
  const gone = useRef(new Set<string>());
  /** Gone ids that a committed render has already left out. */
  const confirmed = useRef(new Set<string>());
  useLayoutEffect(() => {
    latest.current = rendered;
    const shown = new Set(rendered.map((i) => i.id));
    for (const id of gone.current) {
      if (!shown.has(id)) confirmed.current.add(id);
      else if (confirmed.current.has(id)) {
        gone.current.delete(id);
        confirmed.current.delete(id);
      }
    }
  });
  return {
    current: () => latest.current.filter((i) => !gone.current.has(i.id)),
    markDismissed: (id: string) => void gone.current.add(id),
  };
}

/** Navigation state that tags a URL change made by `useLiveSelection().select`. */
interface KeySeqState {
  feedKeySeq?: number;
}

/**
 * The selected id as the keys last left it. navigate() commits in a transition,
 * so the rendered selection can lag a key press (J then K in one frame would
 * otherwise move from the stale row). select() writes here synchronously; each
 * commit syncs it back from the render, except a commit of an earlier key's
 * navigation while a later one is still on its way.
 */
export function useLiveSelection(renderedId: string | null, locationKey: string, locationState: unknown) {
  const live = useRef(renderedId);
  const issued = useRef(0);
  const committed = useRef(0);
  useLayoutEffect(() => {
    const seq = (locationState as KeySeqState | null)?.feedKeySeq;
    if (seq !== undefined && seq > committed.current && seq < issued.current) {
      committed.current = seq;
      return;
    }
    committed.current = seq ?? issued.current;
    live.current = renderedId;
  }, [renderedId, locationKey, locationState]);
  return {
    current: () => live.current,
    /** Record the new selection now and return the navigation state to send with it. */
    select: (id: string | null): KeySeqState => {
      live.current = id;
      issued.current += 1;
      return { feedKeySeq: issued.current };
    },
  };
}
