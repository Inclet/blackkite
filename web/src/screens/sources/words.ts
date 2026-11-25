/**
 * Plain wording for source and admin data (no board: every line here is listed for
 * design review). Health is always said in words, never shown by colour alone.
 */
import type { CollectorType, Health, SourceKind, SourceStatus, SuggestionStatus } from '../../api/sources';
import { STREAM_PLURALS, type Stream } from '../../lib/streams';

export const HEALTH_WORDS: Record<Health, string> = {
  ok: 'Working',
  degraded: 'Some problems',
  failing: 'Failing',
  unknown: 'Not run yet',
};

/** One sentence per health state, for the member Sources page. */
export const HEALTH_HELP: Record<Health, string> = {
  ok: 'Its last checks worked.',
  degraded: 'A recent check failed or found nothing.',
  failing: 'Its last checks failed.',
  unknown: 'It has not been checked yet.',
};

export const KIND_WORDS: Record<SourceKind, string> = {
  original: 'The issuer itself',
  publisher: 'Notice board',
  aggregator: 'Aggregator',
  news: 'News',
  community: 'Community',
};

export const STATUS_WORDS: Record<SourceStatus, string> = {
  suggested: 'Suggested',
  testing: 'Testing',
  active: 'Active',
  paused: 'Paused',
  retired: 'Retired',
};

/** The admin list's groups, in this order. */
export const STATUS_ORDER: readonly SourceStatus[] = ['active', 'testing', 'paused', 'suggested', 'retired'];

export const STATUS_HELP: Record<SourceStatus, string> = {
  active: 'Checked on schedule; members see their items.',
  testing: 'Checked on schedule; their items stay hidden from members.',
  paused: 'Not checked. Items already found stay visible.',
  suggested: 'Not checked yet.',
  retired: 'Not checked. Their items are hidden unless another source carries them.',
};

export const COLLECTOR_WORDS: Record<CollectorType, string> = {
  rss: 'RSS feed',
  html_list: 'Web page list',
  browser_list: 'Web app list (browser)',
  json_api: 'JSON API',
  search_query: 'Search results',
  email_ingest: 'Email alerts',
  custom: 'Custom collector',
};

export const SUGGESTION_WORDS: Record<SuggestionStatus, string> = {
  suggested: 'Waiting for review',
  accepted: 'Accepted',
  rejected: 'Not taken up',
};

export const RUN_WORDS: Record<string, string> = {
  running: 'Running',
  succeeded: 'Worked',
  failed: 'Failed',
};

export function streamList(streams: readonly Stream[]): string {
  return streams.map((s) => STREAM_PLURALS[s] ?? s).join(', ');
}

/** "24 Nov 2026, 08:00" in Kigali time. */
export function formatWhen(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const date = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'Africa/Kigali' }).format(d);
  const time = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'Africa/Kigali' }).format(d);
  return `${date}, ${time}`;
}

/** "24 Nov 2026" in Kigali time. */
export function formatDay(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'Africa/Kigali' }).format(d);
}

export function itemsCount(n: number): string {
  return n === 1 ? '1 item in the last 30 days' : `${n} items in the last 30 days`;
}

/** The promotion gate (spec 4.3 step 4; api sources/service.py PROMOTE_MIN_RUNS). */
export const PROMOTE_MIN_RUNS = 2;

export function gateText(runs: number): string {
  if (runs >= PROMOTE_MIN_RUNS) return `Ready to make active: ${runs} good runs since the last config change.`;
  return `Needs ${PROMOTE_MIN_RUNS} good runs since the last config change: ${runs} so far.`;
}

export const GATE_HELP = 'A good run finished without an error and found at least one item.';
