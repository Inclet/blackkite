import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ItemState } from '../../api/types';
import type { StateCardProps, StateKind } from '../../components/StateCard/StateCard';
import type { FeedContent, FeedItem } from '../../fixtures/types';
import { sortClosingSoonest } from '../../lib/feed';
import type { Stream } from '../../lib/streams';
import { COPY } from '../common/copy';
import type { LoadStateProps } from '../common/LoadState';

const STATES: readonly StateKind[] = ['checking', 'nothing-new', 'first-visit', 'source-down'];

export function stateFromSearch(search: URLSearchParams): StateKind | null {
  const s = search.get('state');
  return STATES.includes(s as StateKind) ? (s as StateKind) : null;
}

/** What the feed screens read: the feed itself and the state cards' copy (the Components board's on fixtures). */
export interface FeedSource {
  feed: FeedContent;
  states: StateCardProps[];
}

/** Persistence for live data. Each call is optimistic: the screen changes first, and is undone if it rejects. */
export interface FeedPersist {
  /** States known from the server (saved and acting from /shortlist). */
  initial: Readonly<Record<string, ItemState>>;
  setState: (item: FeedItem, state: ItemState) => Promise<unknown>;
}

/** Only on live data: the extra detail controls and the status card above the list. */
export interface LiveExtras {
  stateOf: (id: string) => ItemState;
  /** Set acting, done or back to saved; optimistic with rollback. */
  setState: (id: string, state: ItemState) => void;
  /** The loading / unreachable card above the list. */
  status: LoadStateProps;
  /** Set when the last change could not be saved and was undone on screen. */
  failed: boolean;
}

export interface FeedModel extends FeedSource {
  state: StateKind | null;
  /** The state card's content, if a state is shown. */
  stateCard: StateCardProps | null;
  filter: Stream | 'all';
  setFilter: (f: Stream | 'all') => void;
  /** Every item still in the feed (not dismissed), closing soonest first, filter applied. */
  items: FeedItem[];
  byId: (id: string) => FeedItem | undefined;
  saved: ReadonlySet<string>;
  toggleSaved: (id: string) => void;
  dismiss: (id: string) => void;
  /** Polite announcement of the last action (visually hidden). */
  announcement: string;
  live?: LiveExtras;
}

const SAVED: ReadonlySet<ItemState> = new Set(['saved', 'acting']);

const ANNOUNCE: Record<ItemState, string> = {
  saved: 'Saved to shortlist',
  unseen: 'Removed from shortlist',
  dismissed: 'Marked not for me',
  acting: 'Marked as acting on it',
  done: 'Marked done',
};

/**
 * Feed state. Save and dismiss apply to the item across all of the user's
 * profiles (decision 19). On fixtures they are local only; on live data
 * (`persist` given) each change is sent and undone if the server cannot be reached.
 */
export function useFeedModel(
  source: FeedSource,
  state: StateKind | null,
  persist?: FeedPersist,
  status: LoadStateProps = {},
): FeedModel {
  const [filter, setFilter] = useState<Stream | 'all'>('all');
  const [states, setStates] = useState<Readonly<Record<string, ItemState>>>(() => persist?.initial ?? {});
  const [announcement, setAnnouncement] = useState('');
  const [failed, setFailed] = useState(false);

  // States the server reports later (the shortlist loading after the feed) fill in, never overwrite a local change.
  const touched = useRef(new Set<string>());
  const initial = persist?.initial;
  useEffect(() => {
    if (!initial) return;
    setStates((prev) => {
      const next = { ...prev };
      for (const [id, s] of Object.entries(initial)) if (!touched.current.has(id)) next[id] = s;
      return next;
    });
  }, [initial]);

  const all = useMemo(() => {
    let items = source.feed.items;
    // Nothing new: the list is empty. First visit: no profile yet, so nothing is ranked or scored.
    if (state === 'nothing-new') items = [];
    if (state === 'first-visit') items = items.map((i) => ({ ...i, fit: null, topFlag: undefined }));
    return sortClosingSoonest(items);
  }, [source.feed, state]);

  const items = useMemo(
    () => all.filter((i) => states[i.id] !== 'dismissed' && (filter === 'all' || i.stream === filter)),
    [all, states, filter],
  );

  const byId = useCallback((id: string) => all.find((i) => i.id === id), [all]);

  const saved = useMemo(() => new Set(Object.keys(states).filter((id) => SAVED.has(states[id]!))), [states]);

  const statesRef = useRef(states);
  statesRef.current = states;
  const persistRef = useRef(persist);
  persistRef.current = persist;

  const change = useCallback(
    (id: string, next: ItemState) => {
      const item = all.find((i) => i.id === id);
      const before = statesRef.current[id];
      touched.current.add(id);
      setStates((prev) => ({ ...prev, [id]: next }));
      setAnnouncement(`${ANNOUNCE[next]}: ${item?.title ?? id}`);
      const p = persistRef.current;
      if (!p || !item) return;
      setFailed(false);
      p.setState(item, next).catch(() => {
        setStates((prev) => {
          // A later change to the same item wins over this rollback.
          if (prev[id] !== next) return prev;
          const rolled = { ...prev };
          if (before === undefined) delete rolled[id];
          else rolled[id] = before;
          return rolled;
        });
        setFailed(true);
        setAnnouncement(COPY.actionFailed);
      });
    },
    [all],
  );

  const toggleSaved = useCallback((id: string) => change(id, SAVED.has(statesRef.current[id]!) ? 'unseen' : 'saved'), [change]);
  const dismiss = useCallback((id: string) => change(id, 'dismissed'), [change]);

  const stateCard = state ? (source.states.find((s) => s.kind === state) ?? null) : null;

  const live: LiveExtras | undefined = persist
    ? { stateOf: (id) => states[id] ?? 'unseen', setState: change, status, failed }
    : undefined;

  return { ...source, state, stateCard, filter, setFilter, items, byId, saved, toggleSaved, dismiss, announcement, live };
}
