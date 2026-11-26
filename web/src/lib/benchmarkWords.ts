/**
 * Plain wording for awarded-price benchmarks and procurement plans (contract
 * section 6). No board shows these: every line is listed for design review.
 * These numbers are prices, not scores, so showing them is allowed. A sentence
 * only ever holds amounts of one currency.
 */
import { amountOf, type Amount, type BenchmarkCategory, type DetailBenchmark } from '../api/m5';
import { formatAmount } from './detailWords';

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

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

/** "Q1 2027", "March 2027"; text the API sends in another form is kept as written. */
export function plannedWhen(v: string | null | undefined): string | null {
  const t = (v ?? '').trim();
  if (!t) return null;
  let m = t.match(/^(\d{4})-?Q([1-4])$/i) ?? null;
  if (m) return `Q${m[2]} ${m[1]}`;
  m = t.match(/^Q([1-4])[\s-]+(\d{4})$/i);
  if (m) return `Q${m[1]} ${m[2]}`;
  m = t.match(/^(\d{4})-(\d{2})(?:-\d{2})?$/);
  if (m && Number(m[2]) >= 1 && Number(m[2]) <= 12) return `${MONTHS[Number(m[2]) - 1]} ${m[1]}`;
  return t;
}

/** "open_competitive_bidding" -> "Open competitive bidding". */
export function methodWords(v: string | null | undefined): string | null {
  const t = (v ?? '').replace(/_/g, ' ').trim();
  return t ? t[0]!.toUpperCase() + t.slice(1) : null;
}
