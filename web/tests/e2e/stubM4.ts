import type http from 'node:http';

/**
 * The stub's M4 routes (docs/api-contract.md section 5): calendar, the personal
 * calendar feed link, private manual items with share consent, the admin publish
 * step, and the feed's filters. Used by stubApi.ts; same session state.
 *
 * Shapes the contract leaves open follow src/api/m4.ts (feed link `{url}`, items
 * answered like GET /opportunities/{id}, `detail.ownItem` on the owner's items,
 * `GET /api/admin/catalogue?shareable=true`).
 */

/** The run's frozen today (Kigali). */
const TODAY = '2026-11-24';
const STAMP = '2026-11-24T08:00:00Z';

interface Item {
  id: string;
  stream: string;
  title: string;
  organisation: string;
  fit: string | null;
  deadline: string | null;
  [k: string]: unknown;
}

export interface OwnRecord {
  input: Record<string, unknown>;
  shareConsent: boolean;
  visibility: 'private' | 'public';
  changes: Record<string, unknown>[];
}

/** What these routes read and write of a session. */
export interface M4State {
  items: Item[];
  states: Record<string, string>;
  notes: Record<string, string>;
  profiles: Record<string, unknown>[];
  sources: Record<string, unknown>[];
  /** The caller's own manual items, by id. */
  own: Record<string, OwnRecord>;
  /** Bumped by rotate: older feed links stop working. */
  feedLinkVersion: number;
}

/** Times of day the stub's notices state (Kigali), for calendar entries. */
export const CALENDAR_TIMES: Record<string, string> = { 'wfp-logistics': '17:00' };

/** Which stub source carries each default item (for the feed's source filter). */
export const ITEM_SOURCES: Record<string, string[]> = {
  'wfp-logistics': ['src-jir'],
  'tbond-5y': ['src-rse'],
};

function send(res: http.ServerResponse, status: number, body?: unknown): void {
  if (body === undefined) {
    res.writeHead(status).end();
    return;
  }
  res.writeHead(status, { 'Content-Type': 'application/json' }).end(JSON.stringify(body));
}

const day = (iso: string) => Date.UTC(Number(iso.slice(0, 4)), Number(iso.slice(5, 7)) - 1, Number(iso.slice(8, 10))) / 86_400_000;
const daysFromToday = (iso: string) => day(iso) - day(TODAY);
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

function sortDate(i: Item): string | null {
  return i.deadline ?? (i.eventDates as { start?: string } | undefined)?.start ?? null;
}

function closed(i: Item): boolean {
  const ev = i.eventDates as { start: string; end?: string | null } | undefined;
  if (ev) return daysFromToday(ev.end ?? ev.start) < 0;
  return i.deadline !== null && daysFromToday(i.deadline) < 0;
}

const FIT_RANK: Record<string, number> = { strong: 3, good: 2, possible: 1 };
const TRUST_FOR: Record<string, string> = { confirmed: 'confirmed', unconfirmed: 'unconfirmed', conflict: 'conflict' };

/** GET /api/feed's filters (spec 8). Unknown values answer 422, like the API's Literal types. */
export function filterFeed(s: M4State, items: Item[], q: URLSearchParams): Item[] | string {
  let out = items;
  const stream = q.get('stream');
  if (stream) out = out.filter((i) => i.stream === stream);
  const profile = q.get('profile');
  if (profile) {
    const p = s.profiles.find((x) => x.id === profile);
    if (!p) return 'profile: unknown';
    out = out.filter((i) => (i.detail as { profile?: string }).profile === p.name);
  }
  const status = q.get('status');
  if (status) {
    if (!['open', 'closing_soon', 'expired'].includes(status)) return 'status';
    out = out.filter((i) => {
      if (status === 'expired') return closed(i);
      if (closed(i)) return false;
      if (status === 'open') return true;
      const d = sortDate(i);
      return d !== null && daysFromToday(d) <= 7;
    });
  }
  const window = q.get('window');
  if (window) {
    const n = Number(window);
    if (!Number.isInteger(n) || n < 0 || n > 366) return 'window';
    out = out.filter((i) => {
      const d = sortDate(i);
      return d !== null && daysFromToday(d) >= 0 && daysFromToday(d) <= n;
    });
  }
  const fit = q.get('fit');
  if (fit) {
    if (!FIT_RANK[fit]) return 'fit';
    out = out.filter((i) => (FIT_RANK[i.fit ?? ''] ?? 0) >= FIT_RANK[fit]!);
  }
  const source = q.get('source');
  if (source) out = out.filter((i) => (ITEM_SOURCES[i.id] ?? []).includes(source));
  const verification = q.get('verification');
  if (verification) {
    if (!TRUST_FOR[verification]) return 'verification';
    out = out.filter((i) => (i.detail as { trust: { state: string } }).trust.state === verification);
  }
  return out;
}

/** Calendar entries for one item (deadline, or the event's days). */
function entriesOf(i: Item): { date: string; kind: string }[] {
  const ev = i.eventDates as { start: string; end?: string | null } | undefined;
  if (ev) {
    if (!ev.end || ev.end === ev.start) return [{ date: ev.start, kind: 'event' }];
    return [
      { date: ev.start, kind: 'event_start' },
      { date: ev.end, kind: 'event_end' },
    ];
  }
  return i.deadline ? [{ date: i.deadline, kind: 'deadline' }] : [];
}

const ITEM_KEYS = new Set(['stream', 'title', 'organisation', 'deadline', 'eventStart', 'eventEnd', 'value', 'currency', 'location', 'url', 'notes']);
const STREAMS = new Set(['tender', 'investment', 'funding', 'event']);

function itemRefusal(b: Record<string, unknown>, creating: boolean): string | null {
  const extra = Object.keys(b).filter((k) => !ITEM_KEYS.has(k));
  if (extra.length) return `extra keys: ${extra.join(', ')}`;
  if (creating || 'stream' in b) if (!STREAMS.has(String(b.stream))) return 'stream';
  if (creating || 'title' in b) if (typeof b.title !== 'string' || !b.title.trim()) return 'title';
  for (const k of ['deadline', 'eventStart', 'eventEnd']) {
    if (b[k] !== undefined && b[k] !== null && (typeof b[k] !== 'string' || !ISO_DATE.test(b[k] as string))) return `${k}: YYYY-MM-DD`;
  }
  if (b.url !== undefined && b.url !== null && (typeof b.url !== 'string' || !/^https?:\/\/[^/]+\.[^/]+/.test(b.url))) return 'url: http or https only';
  if (b.value !== undefined && b.value !== null && (typeof b.value !== 'number' || b.value < 0)) return 'value';
  if (b.currency !== undefined && b.currency !== null && !['RWF', 'USD', 'EUR'].includes(String(b.currency))) return 'currency';
  return null;
}

const PRIVATE_TRUST = 'You added this item yourself, so nobody else has checked it.';

/** The feed item a manual item shows as. */
function itemFrom(id: string, input: Record<string, unknown>): Item {
  const event = input.stream === 'event' && typeof input.eventStart === 'string';
  return {
    id,
    provisional: false,
    stream: String(input.stream),
    title: String(input.title),
    organisation: typeof input.organisation === 'string' && input.organisation ? input.organisation : 'Added by you',
    fit: null,
    deadline: event ? null : ((input.deadline as string | null | undefined) ?? null),
    ...(event ? { eventDates: { start: input.eventStart, end: (input.eventEnd as string | null) ?? null } } : {}),
    ...(event || input.deadline ? {} : { noDeadlineText: 'No deadline stated' }),
    detail: {
      ...(typeof input.location === 'string' && input.location ? { location: input.location } : {}),
      reasons: [],
      trust: { state: 'unconfirmed', desktop: PRIVATE_TRUST, phone: PRIVATE_TRUST },
      originalUrl: typeof input.url === 'string' ? input.url : '',
    },
  };
}

/** Extra keys GET /opportunities/{id} adds for the caller's own item. */
export function ownExtras(s: M4State, id: string): Record<string, unknown> {
  const own = s.own[id];
  if (!own) return {};
  return { changes: own.changes, ownItem: { input: own.input, shareConsent: own.shareConsent, visibility: own.visibility } };
}

function opportunity(s: M4State, item: Item): Record<string, unknown> {
  return {
    ...item,
    state: s.states[item.id] ?? 'unseen',
    detail: { ...(item.detail as object), fields: [], sources: [], documents: [], note: s.notes[item.id] ?? null, state: s.states[item.id] ?? 'unseen', ...ownExtras(s, item.id) },
  };
}

/** Member routes. Returns false when the path is not one of these. */
export function m4Member(s: M4State, method: string, path: string, q: URLSearchParams, body: unknown, res: http.ServerResponse): boolean {
  const b = (body ?? {}) as Record<string, unknown>;
  if (method === 'GET' && path === '/calendar') {
    const from = q.get('from') ?? '';
    const to = q.get('to') ?? '';
    const kind = q.get('kind') ?? 'all';
    if (!ISO_DATE.test(from) || !ISO_DATE.test(to) || day(to) < day(from)) return send(res, 422, { detail: 'from and to: YYYY-MM-DD' }), true;
    if (day(to) - day(from) > 120) return send(res, 422, { detail: 'The window is at most 120 days.' }), true;
    if (!['deadlines', 'events', 'all'].includes(kind)) return send(res, 422, { detail: 'kind' }), true;
    const savedOnly = q.get('saved') === 'true';
    const byDate = new Map<string, Record<string, unknown>[]>();
    for (const i of s.items) {
      const state = s.states[i.id] ?? 'unseen';
      if (state === 'dismissed') continue;
      if (savedOnly && !['saved', 'acting', 'done'].includes(state)) continue;
      for (const e of entriesOf(i)) {
        if (kind === 'deadlines' && e.kind !== 'deadline') continue;
        if (kind === 'events' && e.kind === 'deadline') continue;
        if (day(e.date) < day(from) || day(e.date) > day(to)) continue;
        const entry: Record<string, unknown> = { id: i.id, stream: i.stream, title: i.title, kind: e.kind, fit: i.fit, state, provisional: Boolean(i.provisional) };
        if (i.organisationShort) entry.organisationShort = i.organisationShort;
        if (CALENDAR_TIMES[i.id] && e.kind === 'deadline') entry.time = CALENDAR_TIMES[i.id];
        byDate.set(e.date, [...(byDate.get(e.date) ?? []), entry]);
      }
    }
    const days = [...byDate.entries()].sort(([a], [c]) => a.localeCompare(c)).map(([date, entries]) => ({ date, entries }));
    return send(res, 200, { days }), true;
  }
  if (method === 'GET' && path === '/calendar/feed-link') {
    return send(res, 200, { url: `https://blackkite.example/api/calendar.ics?token=cal-u1-v${s.feedLinkVersion}` }), true;
  }
  if (method === 'POST' && path === '/calendar/feed-link/rotate') {
    s.feedLinkVersion += 1;
    return send(res, 200, { url: `https://blackkite.example/api/calendar.ics?token=cal-u1-v${s.feedLinkVersion}` }), true;
  }
  if (method === 'POST' && path === '/items') {
    const refused = itemRefusal(b, true);
    if (refused) return send(res, 422, { detail: refused }), true;
    const id = `own-${Object.keys(s.own).length + 1}`;
    const input = Object.fromEntries(Object.entries(b).filter(([, v]) => v !== null && v !== undefined && v !== ''));
    s.own[id] = { input, shareConsent: false, visibility: 'private', changes: [] };
    const item = itemFrom(id, input);
    s.items.push(item);
    if (typeof input.notes === 'string') s.notes[id] = input.notes;
    return send(res, 201, opportunity(s, item)), true;
  }
  const m = path.match(/^\/items\/([^/]+)(\/share-consent)?$/);
  if (!m) return false;
  const id = decodeURIComponent(m[1]!);
  const own = s.own[id];
  // Owner only: anyone else (an admin included) gets 404.
  if (!own) return send(res, 404, { detail: 'Not found' }), true;
  if (method === 'PUT' && m[2]) {
    if (typeof b.allow !== 'boolean' || Object.keys(b).length !== 1) return send(res, 422, { detail: 'allow: true or false' }), true;
    if (own.visibility === 'public') return send(res, 409, { detail: 'Already public' }), true;
    own.shareConsent = b.allow;
    return send(res, 200, { allow: own.shareConsent }), true;
  }
  if (method === 'PATCH' && !m[2]) {
    const refused = itemRefusal(b, false);
    if (refused) return send(res, 422, { detail: refused }), true;
    const next = { ...own.input, ...b };
    own.input = Object.fromEntries(Object.entries(next).filter(([, v]) => v !== null && v !== undefined && v !== ''));
    const i = s.items.findIndex((x) => x.id === id);
    const item = itemFrom(id, own.input);
    s.items[i] = item;
    if ('notes' in b) s.notes[id] = typeof b.notes === 'string' ? b.notes : '';
    return send(res, 200, opportunity(s, item)), true;
  }
  if (method === 'DELETE' && !m[2]) {
    delete s.own[id];
    s.items = s.items.filter((x) => x.id !== id);
    return send(res, 204), true;
  }
  return false;
}

/** Admin routes (the caller is already checked to be an admin). */
export function m4Admin(s: M4State, method: string, p: string, q: URLSearchParams, res: http.ServerResponse): boolean {
  if (method === 'GET' && p === '/catalogue' && q.get('shareable') === 'true') {
    const items = Object.entries(s.own)
      .filter(([, o]) => o.visibility === 'private' && o.shareConsent)
      .map(([id, o]) => ({
        id,
        stream: o.input.stream,
        title: o.input.title,
        organisation: o.input.organisation ?? null,
        status: 'open',
        verification: 'unverified',
        trust: 'unconfirmed',
        needsReview: false,
        reviewReasons: [],
        deadline: o.input.deadline ?? o.input.eventStart ?? null,
        memberVisible: false,
        sources: [],
        createdAt: STAMP,
        updatedAt: STAMP,
        visibility: o.visibility,
        shareConsent: o.shareConsent,
      }));
    return send(res, 200, { total: items.length, items }), true;
  }
  const m = p.match(/^\/catalogue\/([^/]+)\/publish$/);
  if (method === 'POST' && m) {
    const id = decodeURIComponent(m[1]!);
    const own = s.own[id];
    if (!own) return send(res, 404, { detail: 'Opportunity not found' }), true;
    if (!own.shareConsent || own.visibility !== 'private') return send(res, 409, { detail: 'The owner has not allowed this item to be made public.' }), true;
    own.visibility = 'public';
    own.changes = [{ field: 'visibility', old: 'private', new: 'public', at: STAMP }, ...own.changes];
    return send(res, 200, { id, visibility: 'public' }), true;
  }
  return false;
}
