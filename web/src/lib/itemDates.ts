import { formatTime } from './calendar';
import { formatFullDate } from './detailWords';
import { now } from './now';

/**
 * Dates typed into the "Add an item" form, read as the API reads them
 * (api pipeline/dates.py parse_date, pipeline/validate.py check_date): the text
 * must state its year ("7 Dec 2026", "07/12/2026", "2026-12-07", "December 7,
 * 2026"), never guessed; an optional time ("17:00", "5pm", "5:30 pm", "noon")
 * is Kigali time. A date with no time is the end of the day for deadlines and
 * event ends, the start for event starts. It must lie from a year back to two
 * years ahead.
 *
 * The form sends the API one unambiguous form of what was typed: "YYYY-MM-DD",
 * or "YYYY-MM-DDTHH:MM" with a time (Kigali, no zone), which the API reads the same.
 */

export type DayEdge = 'start' | 'end';
export type DateProblem = 'no_year' | 'unparsed' | 'out_of_window';

export interface ItemDate {
  /** Kigali calendar date, YYYY-MM-DD. */
  date: string;
  /** Kigali time, HH:MM, when one was typed. */
  time: string | null;
  /** The instant it stands for (a date alone: start or end of the day). */
  at: Date;
  /** What the API is sent. */
  value: string;
}

const KIGALI_OFFSET_MS = 2 * 3_600_000; // CAT, UTC+2, no daylight saving.
const DAY_MS = 86_400_000;
const EVENT_PAST_MS = 365 * DAY_MS;
const EVENT_FUTURE_MS = 730 * DAY_MS;

const MONTHS: Record<string, number> = {
  jan: 1, january: 1, feb: 2, february: 2, mar: 3, march: 3, apr: 4, april: 4, may: 5, jun: 6, june: 6,
  jul: 7, july: 7, aug: 8, august: 8, sep: 9, sept: 9, september: 9, oct: 10, october: 10, nov: 11, november: 11, dec: 12, december: 12,
};
const MONTH = `(${Object.keys(MONTHS).sort((a, b) => b.length - a.length).join('|')})\\.?`;
const DAY = '(\\d{1,2})(?:st|nd|rd|th)?';
const YEAR = '(\\d{4})';

const ISO_RE = /\b(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?)?/;
const DMY_RE = new RegExp(`\\b${DAY}\\s*(?:of\\s+)?${MONTH}(?:,?\\s*${YEAR}\\b)?`, 'i');
const MDY_RE = new RegExp(`\\b${MONTH}\\s+${DAY}\\b(?:,?\\s*${YEAR}\\b)?`, 'i');
const NUM_RE = /\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4}|\d{2})\b/;
const TIME_RE = /\b(\d{1,2})(?:[:.h](\d{2}))?\s*(a\.?m\.?|p\.?m\.?)|\b(\d{1,2})[:h](\d{2})\b/i;
const NOON_RE = /\bnoon\b|\bmidday\b/i;

type Time = [number, number];

function timeOf(text: string): Time | null {
  if (NOON_RE.test(text)) return [12, 0];
  const m = text.match(TIME_RE);
  if (!m) return null;
  if (m[1] !== undefined) {
    const h = Number(m[1]);
    const min = Number(m[2] ?? 0);
    if (h < 1 || h > 12 || min > 59) return null;
    return [(h % 12) + (m[3]!.toLowerCase().startsWith('p') ? 12 : 0), min];
  }
  const h = Number(m[4]);
  const min = Number(m[5]);
  if (h > 23 || min > 59) return null;
  return [h, min];
}

const pad = (n: number) => String(n).padStart(2, '0');

function realDate(y: number, mo: number, d: number): boolean {
  const t = new Date(Date.UTC(y, mo - 1, d));
  return t.getUTCFullYear() === y && t.getUTCMonth() === mo - 1 && t.getUTCDate() === d;
}

/** A Kigali wall-clock date and time as an instant. */
function kigaliInstant(y: number, mo: number, d: number, h: number, min: number, s = 0): Date {
  return new Date(Date.UTC(y, mo - 1, d, h, min, s) - KIGALI_OFFSET_MS);
}

function build(y: number, mo: number, d: number, time: Time | null, edge: DayEdge): ItemDate {
  const date = `${y}-${pad(mo)}-${pad(d)}`;
  if (time) {
    const hhmm = `${pad(time[0])}:${pad(time[1])}`;
    return { date, time: hhmm, at: kigaliInstant(y, mo, d, time[0], time[1]), value: `${date}T${hhmm}` };
  }
  const at = edge === 'end' ? kigaliInstant(y, mo, d, 23, 59, 59) : kigaliInstant(y, mo, d, 0, 0);
  return { date, time: null, at, value: date };
}

/** The first date-looking match, most specific forms first (as the API searches). */
function search(text: string): { m: RegExpMatchArray; kind: 'iso' | 'num' | 'dmy' | 'mdy' } | null {
  const iso = text.match(ISO_RE);
  if (iso) return { m: iso, kind: 'iso' };
  const num = text.match(NUM_RE);
  if (num) return { m: num, kind: 'num' };
  const dmy = text.match(DMY_RE);
  const mdy = text.match(MDY_RE);
  if (dmy && (!mdy || dmy.index! <= mdy.index!)) return { m: dmy, kind: 'dmy' };
  if (mdy) return { m: mdy, kind: 'mdy' };
  return null;
}

/** Read one typed date. Never invents a year. */
export function parseItemDate(text: string, edge: DayEdge): ItemDate | { problem: 'no_year' | 'unparsed' } {
  const found = search(text);
  if (!found) return { problem: 'unparsed' };
  const { m, kind } = found;
  const start = m.index!;
  const end = start + m[0].length;
  if (kind === 'iso') {
    const [y, mo, d] = [Number(m[1]), Number(m[2]), Number(m[3])];
    if (!realDate(y, mo, d)) return { problem: 'unparsed' };
    if (m[4] === undefined) return build(y, mo, d, timeOf(text.slice(end)), edge);
    const [h, min, s] = [Number(m[4]), Number(m[5]), Number(m[6] ?? 0)];
    if (h > 23 || min > 59 || s > 59) return { problem: 'unparsed' };
    if (!m[7]) return build(y, mo, d, [h, min], edge);
    // A stated zone: the same instant, in Kigali time.
    const offset = m[7] === 'Z' ? 0 : (m[7][0] === '+' ? 1 : -1) * (Number(m[7].slice(1, 3)) * 60 + Number(m[7].slice(-2))) * 60_000;
    const at = new Date(Date.UTC(y, mo - 1, d, h, min, s) - offset);
    const k = new Date(at.getTime() + KIGALI_OFFSET_MS);
    return build(k.getUTCFullYear(), k.getUTCMonth() + 1, k.getUTCDate(), [k.getUTCHours(), k.getUTCMinutes()], edge);
  }
  const [day, month, year] =
    kind === 'num' ? [Number(m[1]), Number(m[2]), m[3]] : kind === 'dmy' ? [Number(m[1]), MONTHS[m[2]!.toLowerCase()]!, m[3]] : [Number(m[2]), MONTHS[m[1]!.toLowerCase()]!, m[3]];
  if (year === undefined) return { problem: 'no_year' };
  const y = Number(year) < 100 ? Number(year) + 2000 : Number(year);
  if (!realDate(y, month, day)) return { problem: 'unparsed' };
  return build(y, month, day, timeOf(`${text.slice(0, start)} ${text.slice(end)}`), edge);
}

/** Read and check a typed date: parsed, with its year, in the API's plausible window. */
export function checkItemDate(text: string, edge: DayEdge, at: Date = now()): ItemDate | { problem: DateProblem } {
  const parsed = parseItemDate(text, edge);
  if ('problem' in parsed) return parsed;
  const t = parsed.at.getTime();
  if (t < at.getTime() - EVENT_PAST_MS || t > at.getTime() + EVENT_FUTURE_MS) return { problem: 'out_of_window' };
  return parsed;
}

/**
 * A stored date as the form shows it for editing: "7 Dec 2026", or
 * "7 Dec 2026, 5pm" when it has a time. The day edge the API filled in for a
 * date typed alone (00:00 for starts, 23:59:59 for ends) reads as the date alone.
 */
export function itemDateText(value: string, edge: DayEdge): string {
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return formatFullDate(value);
  const at = new Date(value);
  if (Number.isNaN(at.getTime())) return value;
  const k = new Date(at.getTime() + KIGALI_OFFSET_MS);
  const date = formatFullDate(`${k.getUTCFullYear()}-${pad(k.getUTCMonth() + 1)}-${pad(k.getUTCDate())}`);
  const [h, min, s] = [k.getUTCHours(), k.getUTCMinutes(), k.getUTCSeconds()];
  if (edge === 'end' && h === 23 && min === 59 && s === 59) return date;
  if (edge === 'start' && h === 0 && min === 0) return date;
  return `${date}, ${formatTime(`${pad(h)}:${pad(min)}`)}`;
}
