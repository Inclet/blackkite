import type http from 'node:http';

/**
 * The stub's M5 routes (docs/api-contract.md section 6): awarded-price
 * benchmarks, a category's awards, planned tenders, and `detail.benchmark` on a
 * tender's page. Used by stubApi.ts; same session state.
 *
 * Shapes as the contract states them (not yet in api-schemas.json):
 *   GET /api/benchmarks?category=&entity=&from=&to=
 *     {categories: [{category, label, awards, median, p25, p75, min, max, currency, medianBidders}]}
 *     statistics null below 3 awards; one entry per (category, currency), never mixed.
 *   GET /api/benchmarks/{category}?limit=&offset=
 *     {awards: [{id, tenderRef, entity, title, winner, winningPrice, bidders: [{name, price}], awardedOn, url}], total}
 *     (`total` and each award's `currency` are the stub's reading; the client also works without them.)
 *   GET /api/plans  {items: [{id, entity, description, method, estimatedValue?, currency?, plannedFor, matchedProfile, url}]}
 *   detail.benchmark {category, median, p25, p75, awards, currency} on tenders whose category has ≥ 3 awards.
 */

export interface StubAward {
  id: string;
  category: string;
  label: string;
  currency: string;
  tenderRef: string | null;
  entity: string;
  title: string;
  winner: string | null;
  winningPrice: number | null;
  bidders: { name: string; price: number | null }[];
  awardedOn: string;
  url: string | null;
}

export interface StubPlan {
  id: string;
  entity: string;
  description: string;
  method: string | null;
  estimatedValue?: number | null;
  currency?: string | null;
  plannedFor: string | null;
  matchedProfile: string;
  url: string | null;
}

export interface M5State {
  items: { id: string; stream: string; [k: string]: unknown }[];
  awards: StubAward[];
  plans: StubPlan[];
  /** Which award category each catalogue tender belongs to. */
  itemCategories: Record<string, string>;
}

function send(res: http.ServerResponse, status: number, body?: unknown): void {
  res.writeHead(status, { 'Content-Type': 'application/json' }).end(JSON.stringify(body));
}

const ENTITIES = ['Rwanda Transport Development Agency', 'World Food Programme', 'Rwanda Agriculture Board', 'City of Kigali'];

/** 23 freight awards over two years (enough to page), 2 road-works awards (too few), software in two currencies. */
export function defaultAwards(): StubAward[] {
  const out: StubAward[] = [];
  for (let i = 0; i < 23; i++) {
    const month = 11 - i; // Nov 2026 back to Jan 2025
    const y = month > 0 ? 2026 : 2025;
    const m = month > 0 ? month : month + 12;
    const price = 3_000_000 + i * 450_000;
    out.push({
      id: `aw-freight-${i + 1}`,
      category: 'freight',
      label: 'Freight and transport',
      currency: 'RWF',
      tenderRef: `RFQ/2026/${String(i + 1).padStart(3, '0')}`,
      entity: ENTITIES[i % ENTITIES.length]!,
      title: `Lot ${i + 1}: transport of goods to district stores`,
      winner: 'Kivu Haulage Ltd',
      winningPrice: price,
      bidders: [
        { name: 'Kivu Haulage Ltd', price },
        { name: 'Hills Transport', price: price + 600_000 },
        { name: 'Lake Freight Co', price: i % 2 ? null : price + 1_100_000 },
      ],
      awardedOn: `${y}-${String(m).padStart(2, '0')}-${String(5 + (i % 20)).padStart(2, '0')}`,
      url: `https://www.umucyo.gov.rw/awards/freight-${i + 1}`,
    });
  }
  out.push(
    { id: 'aw-road-1', category: 'road-works', label: 'Road works', currency: 'RWF', tenderRef: 'RTDA/2026/014', entity: ENTITIES[0]!, title: 'Maintenance of the Kigali–Musanze road', winner: 'Kigali Roads Ltd', winningPrice: 480_000_000, bidders: [{ name: 'Kigali Roads Ltd', price: 480_000_000 }], awardedOn: '2026-09-12', url: 'https://www.umucyo.gov.rw/awards/road-1' },
    { id: 'aw-road-2', category: 'road-works', label: 'Road works', currency: 'RWF', tenderRef: null, entity: ENTITIES[3]!, title: 'Feeder road repairs, Gasabo', winner: null, winningPrice: null, bidders: [], awardedOn: '2026-06-01', url: null },
  );
  for (let i = 0; i < 4; i++) {
    out.push({ id: `aw-it-usd-${i + 1}`, category: 'it-services', label: 'Software and IT services', currency: 'USD', tenderRef: `UNGM/${400 + i}`, entity: 'World Food Programme', title: `Phase ${i + 1} of data platform support`, winner: 'Kigali Data Lab', winningPrice: 40_000 + i * 15_000, bidders: [{ name: 'Kigali Data Lab', price: 40_000 + i * 15_000 }, { name: 'Nairobi Code', price: 52_000 + i * 15_000 }], awardedOn: `2026-0${i + 3}-10`, url: `https://www.ungm.org/Public/Notice/${400 + i}` });
  }
  for (let i = 0; i < 3; i++) {
    out.push({ id: `aw-it-rwf-${i + 1}`, category: 'it-services', label: 'Software and IT services', currency: 'RWF', tenderRef: `MINICT/${i + 1}`, entity: 'City of Kigali', title: `Year ${i + 1} of website and hosting`, winner: 'Irembo Works', winningPrice: 8_000_000 + i * 2_000_000, bidders: [{ name: 'Irembo Works', price: 8_000_000 + i * 2_000_000 }], awardedOn: `2026-0${i + 4}-20`, url: null });
  }
  return out;
}

export function defaultPlans(): StubPlan[] {
  return [
    {
      id: 'pl-rab-cold',
      entity: 'Rwanda Agriculture Board',
      description: 'Cold-chain transport of vaccines and seed to district stores',
      method: 'open_competitive_bidding',
      estimatedValue: 45_000_000,
      currency: 'RWF',
      plannedFor: '2027-Q1',
      matchedProfile: 'Ironji-Trade',
      url: 'https://www.umucyo.gov.rw/plans/rab-2026-27',
    },
    { id: 'pl-cok-data', entity: 'City of Kigali', description: 'Data platform for waste collection rounds', method: 'restricted_tender', plannedFor: '2027-03', matchedProfile: 'AI lab', url: 'https://www.umucyo.gov.rw/plans/cok-2026-27' },
  ];
}

/** The catalogue tenders' award categories. */
export const ITEM_CATEGORIES: Record<string, string> = { 'wfp-logistics': 'freight' };

/** Linear-interpolated quantile of sorted numbers (as PostgreSQL percentile_cont). */
function quantile(sorted: number[], q: number): number {
  const at = (sorted.length - 1) * q;
  const lo = Math.floor(at);
  const hi = Math.ceil(at);
  return sorted[lo]! + (sorted[hi]! - sorted[lo]!) * (at - lo);
}

function stats(awards: StubAward[]) {
  const prices = awards.map((a) => a.winningPrice).filter((p): p is number => p !== null).sort((a, b) => a - b);
  const bidders = awards.map((a) => a.bidders.length).filter((n) => n > 0).sort((a, b) => a - b);
  const enough = awards.length >= 3 && prices.length > 0;
  return {
    awards: awards.length,
    median: enough ? quantile(prices, 0.5) : null,
    p25: enough ? quantile(prices, 0.25) : null,
    p75: enough ? quantile(prices, 0.75) : null,
    min: enough ? prices[0]! : null,
    max: enough ? prices[prices.length - 1]! : null,
    medianBidders: enough && bidders.length ? quantile(bidders, 0.5) : null,
  };
}

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

/** `detail.benchmark` for an item, when it is a tender in a category with ≥ 3 awards (the RWF ones: the API's choice of currency is its own). */
export function m5DetailExtras(s: M5State, itemId: string): Record<string, unknown> {
  const item = s.items.find((i) => i.id === itemId);
  const category = s.itemCategories[itemId];
  if (!item || item.stream !== 'tender' || !category) return {};
  const awards = s.awards.filter((a) => a.category === category && a.currency === 'RWF');
  const st = stats(awards);
  if (st.median === null) return {};
  return { benchmark: { category, median: st.median, p25: st.p25, p75: st.p75, awards: st.awards, currency: 'RWF' } };
}

/** Handle an M5 member route; false when the path is not one of them. */
export function m5Member(s: M5State, method: string, path: string, q: URLSearchParams, res: http.ServerResponse): boolean {
  if (method !== 'GET') return false;
  if (path === '/benchmarks') {
    const from = q.get('from');
    const to = q.get('to');
    if ((from && !ISO_DATE.test(from)) || (to && !ISO_DATE.test(to))) return send(res, 422, { detail: 'from and to: YYYY-MM-DD' }), true;
    const entity = (q.get('entity') ?? '').trim().toLowerCase();
    const category = q.get('category');
    const inWindow = s.awards.filter(
      (a) => (!from || a.awardedOn >= from) && (!to || a.awardedOn <= to) && (!entity || a.entity.toLowerCase().includes(entity)) && (!category || a.category === category),
    );
    const groups = new Map<string, StubAward[]>();
    for (const a of inWindow) groups.set(`${a.category}|${a.currency}`, [...(groups.get(`${a.category}|${a.currency}`) ?? []), a]);
    const categories = [...groups.values()]
      .map((g) => ({ category: g[0]!.category, label: g[0]!.label, currency: g[0]!.currency, ...stats(g) }))
      .sort((a, b) => a.label.localeCompare(b.label) || a.currency.localeCompare(b.currency));
    return send(res, 200, { categories }), true;
  }
  const one = path.match(/^\/benchmarks\/([^/]+)$/);
  if (one) {
    const category = decodeURIComponent(one[1]!);
    const limit = Number(q.get('limit') ?? 50);
    const offset = Number(q.get('offset') ?? 0);
    if (!Number.isInteger(limit) || limit < 1 || limit > 200 || !Number.isInteger(offset) || offset < 0) return send(res, 422, { detail: 'limit 1..200, offset ≥ 0' }), true;
    const all = s.awards.filter((a) => a.category === category).sort((a, b) => b.awardedOn.localeCompare(a.awardedOn));
    // Each award keeps its currency (the contract's award list leaves it out; the client reads it when sent).
    const awards = all.slice(offset, offset + limit).map(({ category: _c, label: _l, ...a }) => a);
    return send(res, 200, { awards, total: all.length }), true;
  }
  if (path === '/plans') return send(res, 200, { items: s.plans }), true;
  return false;
}
