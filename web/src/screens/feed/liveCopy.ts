import type { StateCardProps } from '../../components/StateCard/StateCard';
import type { FeedContent, FeedItem } from '../../fixtures/types';
import { reference } from '../../fixtures/reference';
import { isClosed } from '../../lib/feed';
import { now } from '../../lib/now';

const TIMEZONE = 'Africa/Kigali';

const board = (kind: StateCardProps['kind']) => reference.styleguide.states.find((s) => s.kind === kind)!;

/**
 * What a member with no profiles sees, in place of the board's "Until then you see
 * everything, unranked." (decision 41: tenders and funding need a fit word). Not
 * on the board as written (design review); the Profiles page says the same.
 */
export const UNTIL_PROFILE = 'Until then you see events and investments; tenders and funding need a profile to match against.';

function kigaliMonth(at: Date): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: TIMEZONE, year: 'numeric', month: '2-digit' }).format(at);
}

/** Open shortlist items whose deadline (or event start) falls in this Kigali month. */
export function closingThisMonth(shortlist: FeedItem[], at: Date = now()): number {
  const month = kigaliMonth(at);
  return shortlist.filter((i) => {
    const date = i.deadline ?? i.eventDates?.start;
    return date !== undefined && date !== null && date.slice(0, 7) === month && !isClosed(i, at);
  }).length;
}

function sourcesLine(feed: FeedContent): string {
  const n = feed.sources.checked;
  if (n === 1) return `The 1 source was checked ${feed.sources.when}.`;
  return `All ${n} sources were checked ${feed.sources.when}.`;
}

function shortlistLine(n: number): string {
  if (n === 0) return 'Your shortlist has nothing closing this month.';
  return `Your shortlist has ${n} ${n === 1 ? 'item' : 'items'} closing this month.`;
}

/**
 * The state cards' copy on live data: the Components board's wording, with its
 * counts filled from the feed and the shortlist (the board's "8" and "2").
 * The source-down card is not used here (the feed carries no source health yet).
 */
export function liveStates(feed: FeedContent, shortlist: FeedItem[] | undefined, at: Date = now()): StateCardProps[] {
  const nothing = board('nothing-new');
  const n = feed.sources.checked;
  return [
    { ...board('checking'), title: `Checking ${n} ${n === 1 ? 'source' : 'sources'}` },
    {
      ...nothing,
      body: shortlist ? `${sourcesLine(feed)} ${shortlistLine(closingThisMonth(shortlist, at))}` : sourcesLine(feed),
    },
    { ...board('first-visit'), body: `Three questions about your business or interests. ${UNTIL_PROFILE}` },
  ];
}
