/**
 * M5 member routes (docs/api-contract.md section 6): awarded-price benchmarks by
 * category and planned tenders. Same client as every other route (cookies, JSON,
 * ApiError). Amounts may arrive as numbers or decimal strings ("6000000.00"),
 * as `detail.fields[].value` does; `amountOf` reads either.
 */
import { request } from './client';

const enc = encodeURIComponent;

/** A price as the API sends it: a number, a decimal string, or null when unknown. */
export type Amount = number | string | null;

/** One category of GET /api/benchmarks. Statistics are null when the category has fewer than 3 awards. */
export interface BenchmarkCategory {
  category: string;
  label: string;
  awards: number;
  median: Amount;
  p25: Amount;
  p75: Amount;
  min: Amount;
  max: Amount;
  /** Three letters, as stored (RWF shown as FRW). One currency per entry: amounts are never mixed. */
  currency: string | null;
  medianBidders: number | null;
}

export interface BenchmarksAnswer {
  categories: BenchmarkCategory[];
}

export interface BenchmarksQuery {
  /** YYYY-MM-DD, Kigali; left out for "all". */
  from?: string;
  to?: string;
  entity?: string;
}

export interface Bidder {
  name: string;
  /** Left out or null when the source does not publish it. */
  price?: Amount;
}

/** One award of GET /api/benchmarks/{category}. */
export interface Award {
  id: string;
  tenderRef: string | null;
  entity: string;
  title: string;
  winner: string | null;
  winningPrice: Amount;
  /** Not in the contract's award list; read when sent (the category's currency otherwise). */
  currency?: string | null;
  bidders: Bidder[];
  /** YYYY-MM-DD. */
  awardedOn: string | null;
  url: string | null;
}

export interface AwardsAnswer {
  awards: Award[];
  /** Paged: the count across all pages, when sent. */
  total?: number;
  currency?: string | null;
  label?: string;
}

/** `detail.benchmark` on a tender (GET /api/opportunities/{id}), when its category has at least 3 awards. */
export interface DetailBenchmark {
  category: string;
  median: Amount;
  p25: Amount;
  p75: Amount;
  awards: number;
  currency: string | null;
}

/** One planned tender of GET /api/plans. */
export interface PlanItem {
  id: string;
  entity: string;
  description: string;
  method: string | null;
  estimatedValue?: Amount;
  currency?: string | null;
  /**
   * A calendar quarter ("2027-Q1"), a month ("2027-03"), a date ("2027-03-15") or
   * a start/end range ("2027-03-15/2027-06-30"); other text is shown as written.
   */
  plannedFor: string | null;
  /** The period in plain words ("January to March 2027"), fiscal periods already resolved. Preferred when sent. */
  plannedLabel?: string | null;
  matchedProfile: string | null;
  url: string | null;
}

export interface PlansAnswer {
  items: PlanItem[];
}

/** Awards per page on /benchmarks/{category}. */
export const AWARDS_PAGE = 20;

function query(params: Record<string, string | undefined>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v) q.set(k, v);
  const s = q.toString();
  return s ? `?${s}` : '';
}

/** A price as a number, or null when missing or not a number. */
export function amountOf(v: Amount | undefined): number | null {
  if (v === null || v === undefined || v === '') return null;
  const n = typeof v === 'number' ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

export const m5Api = {
  benchmarks: ({ from, to, entity }: BenchmarksQuery = {}, signal?: AbortSignal) =>
    request<BenchmarksAnswer>(`/api/benchmarks${query({ from, to, entity: entity?.trim() || undefined })}`, { signal }),
  awards: (category: string, page: number, signal?: AbortSignal) =>
    request<AwardsAnswer>(
      `/api/benchmarks/${enc(category)}${query({ limit: String(AWARDS_PAGE), offset: page > 1 ? String((page - 1) * AWARDS_PAGE) : undefined })}`,
      { signal },
    ),
  plans: (signal?: AbortSignal) => request<PlansAnswer>('/api/plans', { signal }),
};
