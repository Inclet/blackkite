import type { DeadlinePillProps } from '../components/DeadlinePill/DeadlinePill';
import type { FeedItem } from '../fixtures/types';
import { daysLeft, eventLabel, formatShortDate } from './deadline';
import { now } from './now';

const TIMEZONE = 'Africa/Kigali';

/** The date the list is ordered by: the deadline, or an event's first day. */
function sortDate(item: FeedItem): string | null {
  return item.deadline ?? item.eventDates?.start ?? null;
}

export function isClosed(item: FeedItem, at: Date = now()): boolean {
  if (item.eventDates) return daysLeft(item.eventDates.end ?? item.eventDates.start, at) < 0;
  return item.deadline !== null && daysLeft(item.deadline, at) < 0;
}

/** "Closing soonest first": open items by date, undated after them, closed items last. */
export function sortClosingSoonest(items: FeedItem[], at: Date = now()): FeedItem[] {
  const rank = (i: FeedItem) => (isClosed(i, at) ? 2 : sortDate(i) === null ? 1 : 0);
  return items
    .map((item, index) => ({ item, index }))
    .sort((a, b) => {
      const r = rank(a.item) - rank(b.item);
      if (r !== 0) return r;
      const da = sortDate(a.item) ?? '';
      const db = sortDate(b.item) ?? '';
      return da < db ? -1 : da > db ? 1 : a.index - b.index;
    })
    .map(({ item }) => item);
}

export function pillFor(item: FeedItem): Omit<DeadlinePillProps, 'className' | 'size'> {
  if (item.eventDates) return { event: item.eventDates };
  return { deadline: item.deadline, emptyText: item.noDeadlineText ?? 'No deadline stated' };
}

const NUMBER_WORDS = ['No', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten', 'Eleven', 'Twelve'];

function countWord(n: number): string {
  return NUMBER_WORDS[n] ?? String(n);
}

/** "Six things worth a look. One closes in 6 days." Counts open deadlines (not events) within 7 days. */
export function feedSummary(items: FeedItem[], at: Date = now()): string {
  const open = items.filter((i) => !isClosed(i, at));
  if (open.length === 0) return 'Nothing to look at right now.';
  const first = `${countWord(open.length)} ${open.length === 1 ? 'thing' : 'things'} worth a look.`;
  const soon = open
    .filter((i) => !i.eventDates && i.deadline !== null && daysLeft(i.deadline, at) <= 7)
    .map((i) => daysLeft(i.deadline!, at))
    .sort((a, b) => a - b);
  if (soon.length === 0) return first;
  if (soon.length === 1) {
    const d = soon[0]!;
    const when = d === 0 ? 'today' : d === 1 ? 'tomorrow' : `in ${d} days`;
    return `${first} One closes ${when}.`;
  }
  return `${first} ${countWord(soon.length)} close within a week.`;
}

function kigaliHour(at: Date): number {
  return Number(new Intl.DateTimeFormat('en-GB', { timeZone: TIMEZONE, hour: '2-digit', hourCycle: 'h23' }).format(at));
}

/** "Good afternoon, Clet"; with no name, just "Good afternoon" (the API sends "" when unset). */
export function greeting(name: string, at: Date = now()): string {
  const h = kigaliHour(at);
  const part = h < 12 ? 'morning' : h < 18 ? 'afternoon' : 'evening';
  const n = name.trim();
  return n ? `Good ${part}, ${n}` : `Good ${part}`;
}

/** The weekly digest goes on Mondays: "Monday 30 November, by email". */
export function nextDigest(channel: string, at: Date = now()): string {
  const parts = new Intl.DateTimeFormat('en-GB', { timeZone: TIMEZONE, weekday: 'short', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(at);
  const get = (t: string) => parts.find((p) => p.type === t)!.value;
  const weekday = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].indexOf(get('weekday'));
  const ahead = (7 - weekday) % 7 || 7;
  const today = Date.UTC(Number(get('year')), Number(get('month')) - 1, Number(get('day')));
  const monday = new Date(today + ahead * 86_400_000);
  const date = new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', weekday: 'long', day: 'numeric', month: 'long' }).format(monday);
  return `${date.replace(',', '')}, by ${channel}`;
}

/** "World Food Programme · Kigali · closes 30 Nov". */
export function detailMeta(item: FeedItem, at: Date = now()): string {
  const parts: string[] = [item.organisation];
  if (item.detail.location && item.detail.location !== item.organisation) parts.push(item.detail.location);
  if (item.eventDates) parts.push(eventLabel(item.eventDates.start, item.eventDates.end));
  else if (item.deadline) parts.push(`${isClosed(item, at) ? 'closed' : 'closes'} ${formatShortDate(item.deadline)}`);
  // An own item may have no organisation: never a leading " · ".
  return parts.filter((p) => p && p.trim()).join(' · ');
}
