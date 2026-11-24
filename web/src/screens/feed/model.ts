import { useCallback, useMemo, useState } from 'react';
import type { StateCardProps, StateKind } from '../../components/StateCard/StateCard';
import type { FeedItem, Fixture } from '../../fixtures/types';
import { sortClosingSoonest } from '../../lib/feed';
import type { Stream } from '../../lib/streams';

const STATES: readonly StateKind[] = ['checking', 'nothing-new', 'first-visit', 'source-down'];

export function stateFromSearch(search: URLSearchParams): StateKind | null {
  const s = search.get('state');
  return STATES.includes(s as StateKind) ? (s as StateKind) : null;
}

export interface FeedModel {
  fixture: Fixture;
  state: StateKind | null;
  /** The state card's content (from the Components board), if a state is shown. */
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
}

/**
 * Fixture-backed feed state. Save and dismiss are local only (no API yet) and
 * apply to the item across all of the user's profiles (decision 19).
 */
export function useFeedModel(fixture: Fixture, state: StateKind | null): FeedModel {
  const [filter, setFilter] = useState<Stream | 'all'>('all');
  const [saved, setSaved] = useState<ReadonlySet<string>>(() => new Set());
  const [dismissed, setDismissed] = useState<ReadonlySet<string>>(() => new Set());
  const [announcement, setAnnouncement] = useState('');

  const all = useMemo(() => {
    let items = fixture.feed.items;
    // Nothing new: the list is empty. First visit: no profile yet, so nothing is ranked or scored.
    if (state === 'nothing-new') items = [];
    if (state === 'first-visit') items = items.map((i) => ({ ...i, fit: null, topFlag: undefined }));
    return sortClosingSoonest(items);
  }, [fixture, state]);

  const items = useMemo(
    () => all.filter((i) => !dismissed.has(i.id) && (filter === 'all' || i.stream === filter)),
    [all, dismissed, filter],
  );

  const byId = useCallback((id: string) => all.find((i) => i.id === id), [all]);

  const toggleSaved = useCallback(
    (id: string) => {
      const item = all.find((i) => i.id === id);
      const was = saved.has(id);
      setSaved((prev) => {
        const next = new Set(prev);
        if (was) next.delete(id);
        else next.add(id);
        return next;
      });
      setAnnouncement(`${was ? 'Removed from' : 'Saved to'} shortlist: ${item?.title ?? id}`);
    },
    [all, saved],
  );

  const dismiss = useCallback(
    (id: string) => {
      const item = all.find((i) => i.id === id);
      setDismissed((prev) => new Set(prev).add(id));
      setAnnouncement(`Marked not for me: ${item?.title ?? id}`);
    },
    [all],
  );

  const stateCard = state ? (fixture.styleguide.states.find((s) => s.kind === state) ?? null) : null;

  return { fixture, state, stateCard, filter, setFilter, items, byId, saved, toggleSaved, dismiss, announcement };
}
