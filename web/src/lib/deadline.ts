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

export function formatShortDate(isoDate: string): string {
  const [y, m, d] = isoDate.slice(0, 10).split('-').map(Number);
  return new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' }).format(new Date(Date.UTC(y!, m! - 1, d!)));
}

export function deadlineLabel(deadline: string, at: Date = now()): string {
  const days = daysLeft(deadline, at);
  if (days < 0) return `Closed ${formatShortDate(deadline)}`;
  if (days === 0) return 'Closes today';
  if (days === 1) return 'Closes tomorrow';
  return `${days} days left`;
}
