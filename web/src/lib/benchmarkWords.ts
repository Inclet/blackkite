/**
 * Plain wording for awarded-price benchmarks and procurement plans (contract
 * section 6). No board shows these: every line is listed for design review.
 * These numbers are prices, not scores, so showing them is allowed. A sentence
 * only ever holds amounts of one currency.
 */
import { amountOf, type Amount, type BenchmarkCategory, type DetailBenchmark } from '../api/m5';
import { formatAmount } from './detailWords';
import { dayMonthYear, LONG_MONTHS } from './months';

/** RWF is written FRW, as everywhere else in Blackkite. */
export function currencyWord(currency: string | null | undefined): string {
  return !currency || currency.toUpperCase() === 'RWF' ? 'FRW' : currency.toUpperCase();
}

const oneDecimal = (n: number) => {
  const t = n.toFixed(1);
  return t.endsWith('.0') ? t.slice(0, -2) : t;
};

/**
 * "FRW 4.2M", "FRW 1.5B", "USD 48,500": a million and up abbreviated to one
 * decimal, smaller amounts in full with separators.
 */
export function shortAmount(amount: number, currency: string | null | undefined): string {
  const c = currencyWord(currency);
  const abs = Math.abs(amount);
  if (abs >= 1e6) {
    const m = Number(oneDecimal(amount / 1e6));
    if (Math.abs(m) < 1000) return `${c} ${oneDecimal(amount / 1e6)}M`;
    return `${c} ${oneDecimal(amount / 1e9)}B`;
  }
  return `${c} ${new Intl.NumberFormat('en-GB', { maximumFractionDigits: 0 }).format(Math.round(amount))}`;
}

/** A full price for one award: "FRW 6,120,000". */
export function fullAmount(v: Amount | undefined, currency: string | null | undefined): string | null {
  const n = amountOf(v);
  return n === null ? null : formatAmount(n, currencyWord(currency) === 'FRW' ? 'RWF' : currencyWord(currency));
}

const count = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
export const awardsWord = (n: number) => count(n, 'award', 'awards');

/** Fewer awards than this and no range is shown (contract: statistics need at least 3). */
export const MIN_AWARDS = 3;

/** "between FRW 4.2M and FRW 9.8M", or "about FRW 4.2M" when both ends read the same. Null without both ends. */
function between(p25: Amount, p75: Amount, currency: string | null): string | null {
  const lo = amountOf(p25);
  const hi = amountOf(p75);
  if (lo === null || hi === null) return null;
  const a = shortAmount(lo, currency);
  const b = shortAmount(hi, currency);
  return a === b ? `about ${a}` : `between ${a} and ${b}`;
}

export const BENCHMARK_COPY = {
  tooFew: (n: number) => (n === 0 ? 'No awards in this period yet.' : `Only ${awardsWord(n)} so far — not enough to show a range.`),
  bidders: (n: number) => `Usually ${count(n, 'bidder', 'bidders')}.`,
} as const;

/**
 * One category in plain words: "Most awards were between FRW 4.2M and FRW 9.8M;
 * the middle one was FRW 6.1M (14 awards). Usually 5 bidders."
 */
export function categorySentence(c: BenchmarkCategory): string {
  const range = c.awards >= MIN_AWARDS ? between(c.p25, c.p75, c.currency) : null;
  if (!range) return c.awards >= MIN_AWARDS ? `${awardsWord(c.awards)} so far.` : BENCHMARK_COPY.tooFew(c.awards);
  const median = amountOf(c.median);
  const middle = median === null ? '' : `; the middle one was ${shortAmount(median, c.currency)}`;
  const bidders = c.medianBidders !== null && c.medianBidders !== undefined && c.medianBidders > 0 ? ` ${BENCHMARK_COPY.bidders(Math.round(c.medianBidders))}` : '';
  return `Most awards were ${range}${middle} (${awardsWord(c.awards)}).${bidders}`;
}

/** The tender detail's line: "Similar contracts were usually awarded between FRW 4.2M and FRW 9.8M (14 awards)." Null when there is no range. */
export function detailBenchmarkSentence(b: DetailBenchmark | null | undefined): string | null {
  if (!b || b.awards < MIN_AWARDS) return null;
  const range = between(b.p25, b.p75, b.currency);
  return range ? `Similar contracts were usually awarded ${range} (${awardsWord(b.awards)}).` : null;
}

/** A category slug as words, when no label is known: "road-works" -> "Road works". */
export function categoryFallbackLabel(category: string): string {
  const t = category.replace(/[-_]+/g, ' ').trim();
  return t ? t[0]!.toUpperCase() + t.slice(1) : category;
}

export type Period = '12m' | '2y' | 'all';
export const PERIODS: readonly Period[] = ['12m', '2y', 'all'];
export const PERIOD_WORDS: Record<Period, string> = { '12m': '12 months', '2y': '2 years', all: 'All' };

/** The window's first day (YYYY-MM-DD) for a period ending on `today` (YYYY-MM-DD); undefined for all. */
export function periodFrom(period: Period, today: string): string | undefined {
  if (period === 'all') return undefined;
  const years = period === '12m' ? 1 : 2;
  const [y, m, d] = today.split('-').map(Number);
  const at = new Date(Date.UTC(y! - years, m! - 1, d!));
  // 29 Feb a year on: the day after 28 Feb.
  return at.toISOString().slice(0, 10);
}

const ISO_DAY = /^(\d{4})-(\d{2})-(\d{2})$/;
const ISO_MONTH = /^(\d{4})-(\d{2})$/;

/** A real calendar date as YYYY-MM-DD, or null. */
function validDay(t: string): { y: number; m: number; d: number } | null {
  const m = t.match(ISO_DAY);
  if (!m) return null;
  const [y, mo, d] = [Number(m[1]), Number(m[2]), Number(m[3])];
  const at = new Date(Date.UTC(y, mo - 1, d));
  return at.getUTCFullYear() === y && at.getUTCMonth() === mo - 1 && at.getUTCDate() === d ? { y, m: mo, d } : null;
}

const lastDay = (y: number, m: number) => new Date(Date.UTC(y, m, 0)).getUTCDate();

/** "January to March 2027", "October 2026 to March 2027"; one month alone as "March 2027". */
function monthSpan(y1: number, m1: number, y2: number, m2: number): string {
  if (y1 === y2 && m1 === m2) return `${LONG_MONTHS[m1 - 1]} ${y1}`;
  if (y1 === y2) return `${LONG_MONTHS[m1 - 1]} to ${LONG_MONTHS[m2 - 1]} ${y2}`;
  return `${LONG_MONTHS[m1 - 1]} ${y1} to ${LONG_MONTHS[m2 - 1]} ${y2}`;
}

/** A calendar quarter as its months: Q1 2027 -> "January to March 2027". */
const quarterWords = (y: number, q: number) => monthSpan(y, q * 3 - 2, y, q * 3);

/**
 * When a planned tender is due, in words. The API's `plannedLabel` comes first
 * (it knows fiscal from calendar periods). Otherwise `plannedFor` is read: a date
 * as "17 Feb 2027", a month as "March 2027", a calendar quarter as "January to
 * March 2027", a start/end range as "{start} to {end}" (whole months as months).
 * Never raw ISO: ISO-looking text that does not parse is left out; other text is
 * kept as written.
 */
export function plannedWhen(v: string | null | undefined, label?: string | null): string | null {
  const l = (label ?? '').trim();
  if (l) return l;
  const t = (v ?? '').trim();
  if (!t) return null;
  let m = t.match(/^(\d{4})-?Q([1-4])$/i) ?? null;
  if (m) return quarterWords(Number(m[1]), Number(m[2]));
  m = t.match(/^Q([1-4])[\s-]+(\d{4})$/i);
  if (m) return quarterWords(Number(m[2]), Number(m[1]));
  m = t.match(ISO_MONTH);
  if (m) return Number(m[2]) >= 1 && Number(m[2]) <= 12 ? monthSpan(Number(m[1]), Number(m[2]), Number(m[1]), Number(m[2])) : null;
  const day = validDay(t);
  if (day) return dayMonthYear(t);
  const range = t.split('/');
  if (range.length === 2 && /^\d{4}-\d{2}/.test(range[0]!.trim())) {
    const a = validDay(range[0]!.trim());
    const b = validDay(range[1]!.trim());
    if (!a || !b) return null;
    if (range[0]!.trim() === range[1]!.trim()) return dayMonthYear(range[0]!.trim());
    if (a.d === 1 && b.d === lastDay(b.y, b.m)) return monthSpan(a.y, a.m, b.y, b.m);
    return `${dayMonthYear(range[0]!.trim())} to ${dayMonthYear(range[1]!.trim())}`;
  }
  return /^\d{4}-\d{2}/.test(t) ? null : t;
}

/** "open_competitive_bidding" -> "Open competitive bidding". */
export function methodWords(v: string | null | undefined): string | null {
  const t = (v ?? '').replace(/_/g, ' ').trim();
  return t ? t[0]!.toUpperCase() + t.slice(1) : null;
}
