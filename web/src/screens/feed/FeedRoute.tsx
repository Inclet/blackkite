import { useCallback, useMemo } from 'react';
import { useMatch, useSearchParams } from 'react-router';
import { api } from '../../api/client';
import type { DismissReason, ItemState, LiveFeedItem } from '../../api/types';
import { useResource } from '../../api/useResource';
import type { StateKind } from '../../components/StateCard/StateCard';
import type { FeedItem, Fixture } from '../../fixtures/types';
import { fixtureFromSearch } from '../../lib/fixture';
import { useIsDesktop } from '../../lib/useIsDesktop';
import { LoadState, type LoadStateProps } from '../common/LoadState';
import { AppShell } from '../shell/AppShell';
import { SignIn } from '../SignIn';
import { FeedDesktop } from './FeedDesktop';
import { FeedPhone } from './FeedPhone';
import { liveStates } from './liveCopy';
import { stateFromSearch, useFeedModel, type FeedPersist, type FeedSource } from './model';
import { OpportunityPhone } from './OpportunityPhone';
import { useDismissPromptLifetime } from './parts';

/**
 * Layout route for / and /o/:id. The feed state lives here so it survives
 * moving between the two (J/K change the URL without a reload).
 * With ?fixture=<name> the screens use that fixture, exactly as the boards;
 * without it they load from the member API.
 */
export function FeedRoute() {
  const [search] = useSearchParams();
  const fixture = fixtureFromSearch(search);
  const match = useMatch('/o/:id');
  const openId = match?.params.id ?? null;
  if (!fixture) return <LiveFeed openId={openId} />;
  return <FixtureFeed fixture={fixture} openId={openId} state={stateFromSearch(search)} />;
}

function FixtureFeed({ fixture, openId, state }: { fixture: Fixture; openId: string | null; state: StateKind | null }) {
  const source = useMemo(() => ({ feed: fixture.feed, states: fixture.styleguide.states }), [fixture]);
  return <FeedScreens model={useFeedModel(source, state)} openId={openId} />;
}

function FeedScreens({ model, openId }: { model: ReturnType<typeof useFeedModel>; openId: string | null }) {
  const desktop = useIsDesktop();
  useDismissPromptLifetime(model);
  if (desktop) return <FeedDesktop model={model} openId={openId} />;
  if (openId) return <OpportunityPhone model={model} id={openId} />;
  return <FeedPhone model={model} />;
}

/** Each feed item carries the caller's state (contract section 2); the feed is the source of truth. */
export function statesFrom(feedItems: LiveFeedItem[]): Record<string, ItemState> {
  const out: Record<string, ItemState> = {};
  for (const i of feedItems) if (i.state !== 'unseen') out[i.id] = i.state;
  return out;
}

function LiveFeed({ openId }: { openId: string | null }) {
  const feed = useResource('feed', (s) => api.feed({}, s));
  const shortlist = useResource('shortlist', (s) => api.shortlist(s));
  const profiles = useResource('profiles', (s) => api.profiles(s));
  const errors = [feed.error, shortlist.error, profiles.error];

  const retry = useCallback(() => {
    feed.reload();
    shortlist.reload();
    profiles.reload();
  }, [feed.reload, shortlist.reload, profiles.reload]);

  if (errors.some((e) => e?.kind === 'unauthorized')) return <SignIn />;

  if (!feed.data) {
    return (
      <AppShell path={openId ? `/o/${openId}` : '/'} title="Feed">
        <LoadState loading={feed.loading} error={feed.error} onRetry={retry} />
      </AppShell>
    );
  }

  const error = errors.find((e) => e !== null) ?? null;
  const status: LoadStateProps = { refreshing: feed.refreshing || shortlist.refreshing || profiles.refreshing, error, onRetry: retry };
  return (
    <LiveFeedScreens
      feed={feed}
      shortlist={shortlist}
      firstVisit={profiles.data !== undefined && profiles.data.length === 0}
      status={status}
      openId={openId}
    />
  );
}

type FeedResource = ReturnType<typeof useResource<Awaited<ReturnType<typeof api.feed>>>>;
type ShortlistResource = ReturnType<typeof useResource<LiveFeedItem[]>>;

function LiveFeedScreens({
  feed,
  shortlist,
  firstVisit,
  status,
  openId,
}: {
  feed: FeedResource;
  shortlist: ShortlistResource;
  firstVisit: boolean;
  status: LoadStateProps;
  openId: string | null;
}) {
  const content = feed.data!;
  const source: FeedSource = useMemo(() => ({ feed: content, states: liveStates(content, shortlist.data) }), [content, shortlist.data]);
  const initial = useMemo(() => statesFrom(content.items), [content.items]);

  const { setData: setShortlist } = shortlist;
  const { setData: setFeed } = feed;
  const persist: FeedPersist = useMemo(
    () => ({
      initial,
      setState: async (item: FeedItem, state: ItemState) => {
        await api.setState(item.id, state);
        // Keep the cached shortlist and feed in step, so the next screen starts from the truth.
        setShortlist((prev) => {
          const rest = (prev ?? []).filter((i) => i.id !== item.id);
          return state === 'saved' || state === 'acting' ? [...rest, { ...item, state, provisional: item.provisional ?? false }] : rest;
        });
        setFeed((prev) => {
          if (!prev) return prev;
          const items: LiveFeedItem[] = prev.items;
          return {
            ...prev,
            items: state === 'dismissed' ? items.filter((i) => i.id !== item.id) : items.map((i) => (i.id === item.id ? { ...i, state } : i)),
          };
        });
      },
      setDismissReason: (item: FeedItem, reason: DismissReason) => api.setState(item.id, 'dismissed', reason),
      forget: (id: string) => {
        setShortlist((prev) => prev?.filter((i) => i.id !== id));
        setFeed((prev) => prev && { ...prev, items: (prev.items as LiveFeedItem[]).filter((i) => i.id !== id) });
      },
    }),
    [initial, setShortlist, setFeed],
  );

  const model = useFeedModel(source, firstVisit ? 'first-visit' : null, persist, status);
  return <FeedScreens model={model} openId={openId} />;
}
