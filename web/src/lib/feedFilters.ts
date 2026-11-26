import type { FeedQuery } from '../api/client';

/**
 * The feed's filters beyond the stream chips (spec 8): in the URL query under the
 * API's own names, so a filtered feed can be shared and reloaded. Fit is a word,
 * never a number (spec 12).
 */
export type FilterKey = 'profile' | 'status' | 'window' | 'fit' | 'source' | 'verification';

export const FILTER_KEYS: readonly FilterKey[] = ['profile', 'status', 'window', 'fit', 'source', 'verification'];

/** Group labels and the fixed choices. Profile and source choices come from the API. Not on any board (design review). */
export const FILTER_COPY = {
  button: 'Filters',
  buttonCount: (n: number) => `Filters (${n})`,
  panel: 'Filter the feed',
  any: 'Any',
  anyProfile: 'All profiles',
  anySource: 'Any source',
  applied: 'Applied filters. Press one to remove it.',
  remove: (group: string, value: string) => `Remove filter ${group}: ${value}`,
  clear: 'Clear filters',
  groups: { profile: 'Profile', status: 'Status', window: 'Deadline', fit: 'Fit', source: 'Source', verification: 'Trust' } satisfies Record<FilterKey, string>,
} as const;

export const FIXED_CHOICES = {
  status: [
    ['open', 'Open'],
    ['closing_soon', 'Closing soon'],
    ['expired', 'Closed'],
  ],
  window: [
    ['7', 'This week'],
    ['14', '2 weeks'],
    ['30', 'Month'],
  ],
  fit: [
    ['strong', 'Strong'],
    ['good', 'Good and up'],
    ['possible', 'Possible and up'],
  ],
  verification: [
    ['confirmed', 'Confirmed at the source'],
    ['unconfirmed', 'Not yet confirmed'],
    ['conflict', 'Sources disagree'],
  ],
} as const satisfies Partial<Record<FilterKey, readonly (readonly [string, string])[]>>;

const ID = /^[\w-]{1,64}$/;

/** The filters in a URL query, keeping only values the API accepts. */
export function readFilters(search: URLSearchParams): FeedQuery {
  const out: FeedQuery = {};
  for (const key of FILTER_KEYS) {
    const v = search.get(key);
    if (!v) continue;
    if (key === 'profile' || key === 'source') {
      if (ID.test(v)) out[key] = v;
      continue;
    }
    if ((FIXED_CHOICES[key] as readonly (readonly [string, string])[]).some(([value]) => value === v)) out[key] = v;
  }
  return out;
}

/** The query string the feed resource is keyed by ("" when unfiltered), in a fixed order. */
export function filterQuery(f: FeedQuery): string {
  const q = new URLSearchParams();
  for (const key of FILTER_KEYS) if (f[key]) q.set(key, f[key]!);
  return q.toString();
}

/** A filter value in words (profile and source names looked up). */
export function filterWord(key: FilterKey, value: string, names: { profiles: Record<string, string>; sources: Record<string, string> }): string {
  if (key === 'profile') return names.profiles[value] ?? 'A profile';
  if (key === 'source') return names.sources[value] ?? 'A source';
  return (FIXED_CHOICES[key] as readonly (readonly [string, string])[]).find(([v]) => v === value)?.[1] ?? value;
}
