import { kigaliToday } from './deadline';
import { now } from './now';

/** A month as YYYY-MM. */
export type Month = string;

const MONTH = /^(\d{4})-(0[1-9]|1[0-2])$/;

export function currentMonth(at: Date = now()): Month {
  return kigaliToday(at).slice(0, 7);
}

/** ?month=YYYY-MM, or this month (Kigali) when absent or malformed. */
export function parseMonth(raw: string | null, at: Date = now()): Month {
  return raw && MONTH.test(raw) ? raw : currentMonth(at);
}

function parts(month: Month): [number, number] {
  return [Number(month.slice(0, 4)), Number(month.slice(5, 7))];
}

const pad = (n: number) => String(n).padStart(2, '0');

export function shiftMonth(month: Month, by: number): Month {
  const [y, m] = parts(month);
  const d = new Date(Date.UTC(y, m - 1 + by, 1));
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}`;
}

export function daysInMonth(month: Month): number {
  const [y, m] = parts(month);
  return new Date(Date.UTC(y, m, 0)).getUTCDate();
}

/** The API window for a month: first to last day. */
export function monthRange(month: Month): { from: string; to: string } {
  return { from: `${month}-01`, to: `${month}-${pad(daysInMonth(month))}` };
}

/** "November 2026". */
export function monthTitle(month: Month): string {
  const [y, m] = parts(month);
  return new Intl.DateTimeFormat('en-GB', { month: 'long', year: 'numeric', timeZone: 'UTC' }).format(new Date(Date.UTC(y, m - 1, 1)));
}

function utc(iso: string): Date {
  return new Date(Date.UTC(Number(iso.slice(0, 4)), Number(iso.slice(5, 7)) - 1, Number(iso.slice(8, 10))));
}

/** "Tuesday 24 November 2026": full dates, with the year (spec 2.5). */
export function dayTitle(iso: string): string {
  return new Intl.DateTimeFormat('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' })
    .format(utc(iso))
    .replace(',', '');
}

/** Monday-first weekday names, as the grid's column headings. */
export const WEEKDAYS = [
  { short: 'Mon', long: 'Monday' },
  { short: 'Tue', long: 'Tuesday' },
  { short: 'Wed', long: 'Wednesday' },
  { short: 'Thu', long: 'Thursday' },
  { short: 'Fri', long: 'Friday' },
  { short: 'Sat', long: 'Saturday' },
  { short: 'Sun', long: 'Sunday' },
] as const;

/** The month as weeks of seven cells, Monday first; cells outside the month are null. */
export function monthWeeks(month: Month): (string | null)[][] {
  const first = utc(`${month}-01`);
  const lead = (first.getUTCDay() + 6) % 7;
  const cells: (string | null)[] = Array.from({ length: lead }, () => null);
  for (let d = 1; d <= daysInMonth(month); d++) cells.push(`${month}-${pad(d)}`);
  while (cells.length % 7) cells.push(null);
  const weeks: (string | null)[][] = [];
  for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7));
  return weeks;
}

/** "17:00" → "5pm", "09:30" → "9:30am"; anything else as sent. */
export function formatTime(time: string): string {
  const m = time.match(/^(\d{1,2}):(\d{2})/);
  if (!m) return time;
  const h = Number(m[1]);
  const min = m[2]!;
  const suffix = h < 12 ? 'am' : 'pm';
  const h12 = h % 12 === 0 ? 12 : h % 12;
  return min === '00' ? `${h12}${suffix}` : `${h12}:${min}${suffix}`;
}

/** Add days to a YYYY-MM-DD date. */
export function addDays(iso: string, n: number): string {
  const d = utc(iso);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}
