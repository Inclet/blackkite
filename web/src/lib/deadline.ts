import { dayMonth } from './months';
import { now } from './now';

/** Deadlines are calendar dates in Kigali. */
const TIMEZONE = 'Africa/Kigali';

export type DeadlineWeight = 'quiet' | 'outlined' | 'solid' | 'alert';

/** Today's date in Kigali as YYYY-MM-DD. */
export function kigaliToday(at: Date = now()): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: TIMEZONE, year: 'numeric', month: '2-digit', day: '2-digit' }).format(at);
}

function dayNumber(isoDate: string): number {
  const [y, m, d] = isoDate.slice(0, 10).split('-').map(Number);
  return Date.UTC(y!, m! - 1, d!) / 86_400_000;
}

/** Whole days from today (Kigali) to the deadline date: 0 on the day, negative once closed. */
export function daysLeft(deadline: string, at: Date = now()): number {
  return dayNumber(deadline) - dayNumber(kigaliToday(at));
}

/**
 * Over 14 days quiet, 14 or fewer outlined, 7 or fewer solid, the last day alert.
 * "Last day" follows the Foundations board, which draws "Closes tomorrow" in alert:
 * the day before and the day itself.
 */
export function deadlineWeight(days: number): DeadlineWeight {
  if (days <= 1) return 'alert';
  if (days <= 7) return 'solid';
  if (days <= 14) return 'outlined';
  return 'quiet';
}

/** "17 Sep": the app's short month style (lib/months). */
export function formatShortDate(isoDate: string): string {
  return dayMonth(isoDate);
}

export function deadlineLabel(deadline: string, at: Date = now()): string {
  const days = daysLeft(deadline, at);
  if (days < 0) return `Closed ${formatShortDate(deadline)}`;
  if (days === 0) return 'Closes today';
  if (days === 1) return 'Closes tomorrow';
  return `${days} days left`;
}

/**
 * Event pills, counted from event_start (decision 23): over 14 days quiet,
 * 7 to 14 outlined, 6 or fewer solid, the day before or the day itself alert.
 * An event that has started and not ended stays alert.
 */
export function eventWeight(daysToStart: number): DeadlineWeight {
  if (daysToStart <= 1) return 'alert';
  if (daysToStart <= 6) return 'solid';
  if (daysToStart <= 14) return 'outlined';
  return 'quiet';
}

function monthOf(isoDate: string): string {
  return isoDate.slice(0, 7);
}

/** "1 Dec", "1 to 2 Dec", "30 Nov to 2 Dec". */
export function eventLabel(start: string, end?: string | null): string {
  if (!end || end.slice(0, 10) === start.slice(0, 10)) return formatShortDate(start);
  const startDay = Number(start.slice(8, 10));
  if (monthOf(start) === monthOf(end)) return `${startDay} to ${formatShortDate(end)}`;
  return `${formatShortDate(start)} to ${formatShortDate(end)}`;
}

/** True once the last day of the event has passed. */
export function eventEnded(start: string, end?: string | null, at: Date = now()): boolean {
  return daysLeft(end ?? start, at) < 0;
}
