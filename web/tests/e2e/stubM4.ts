import type http from 'node:http';

/**
 * The stub's M4 routes (docs/api-contract.md section 5): calendar, the personal
 * calendar feed link, private manual items with share consent, the admin publish
 * step, and the feed's filters. Used by stubApi.ts; same session state.
 *
 * Shapes as built (contract section 5; checked against api-schemas.json in
 * tests/contract/stub.m4.test.ts): CalendarOut, FeedLinkOut, OpportunityOut with
 * `detail.ownItem {shareConsent, published}`, ShareConsentOut, CatalogueItem.
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
  shareConsentAt: string | null;
  published: boolean;
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
  /** Bumped by rotate: older feed links stop working. 0 = the server has no calendar secret (503). */
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
/** What the item form sends for a typed date: the day, or the day and a Kigali time (the API reads any text with a year). */
const ITEM_DATE = /^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2})?$/;
const dayOf = (v: unknown) => (typeof v === 'string' ? v.slice(0, 10) : null);
/** The stored instant: a timed value as typed, a day alone at its start or end (Kigali). */
const instant = (v: string, edge: 'start' | 'end') => (v.includes('T') ? `${v}:00+02:00` : `${v}T${edge === 'end' ? '23:59:59' : '00:00:00'}+02:00`);

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
  // Repeatable: any of the statuses (contract section 5, built).
  const statuses = q.getAll('status');
  if (statuses.length) {
    if (statuses.some((x) => !['open', 'closing_soon', 'expired', 'awarded', 'cancelled'].includes(x))) return 'status';
    const statusOf = (i: Item) => {
      if (closed(i)) return 'expired';
      const d = sortDate(i);
      return d !== null && daysFromToday(d) <= 7 ? 'closing_soon' : 'open';
    };
    out = out.filter((i) => statuses.includes(statusOf(i)));
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

interface Problem {
  field: string | null;
  message: string;
}

const LABELS: Record<string, string> = { stream: 'Stream', title: 'Title', deadline: 'Deadline', eventStart: 'Event start', eventEnd: 'Event end', url: 'Link', value: 'Value', currency: 'Currency' };

/** 422 RefusalOut {detail, errors}, in plain words (contract 4.1, 5). */
function refusal(problems: Problem[]) {
  return { detail: problems.map((p) => `${p.field ? LABELS[p.field] ?? p.field : 'Item'}: ${p.message}.`).join(' '), errors: problems };
}

/** A year back to two years ahead of the frozen today, as the API's plausible window. */
const inWindow = (iso: string) => iso >= '2025-11-24' && iso <= '2028-11-24';

function itemRefusal(b: Record<string, unknown>, creating: boolean, stream: unknown): Problem[] {
  const out: Problem[] = [];
  const extra = Object.keys(b).filter((k) => !ITEM_KEYS.has(k));
  if (extra.length) out.push({ field: null, message: `unknown fields ${extra.join(', ')}` });
  if (creating || 'stream' in b) if (!STREAMS.has(String(b.stream))) out.push({ field: 'stream', message: 'choose tender, investment, funding or event' });
  if (creating || 'title' in b) if (typeof b.title !== 'string' || !b.title.trim()) out.push({ field: 'title', message: 'is required' });
  for (const k of ['deadline', 'eventStart', 'eventEnd']) {
    const v = b[k];
    if (v === undefined || v === null) continue;
    if (typeof v !== 'string' || !ITEM_DATE.test(v)) out.push({ field: k, message: 'include the year, for example 30 Nov 2026' });
    else if (!inWindow(v.slice(0, 10))) out.push({ field: k, message: 'must be between a year ago and two years from now' });
  }
  if ((b.eventStart || b.eventEnd) && stream !== 'event') out.push({ field: 'eventStart', message: 'only events have event dates' });
  if (b.eventEnd && !b.eventStart) out.push({ field: 'eventEnd', message: 'needs a start date' });
  if (b.url !== undefined && b.url !== null && (typeof b.url !== 'string' || !/^https?:\/\/[^/\s]+\.[^/\s]+/.test(b.url))) out.push({ field: 'url', message: 'use a web address starting with https://' });
  if (b.value !== undefined && b.value !== null && (typeof b.value !== 'number' || b.value < 0)) out.push({ field: 'value', message: 'use a number' });
  if (b.currency !== undefined && b.currency !== null && !/^[A-Za-z]{3}$/.test(String(b.currency))) out.push({ field: 'currency', message: 'use three letters, such as RWF' });
  return out;
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
    organisation: typeof input.organisation === 'string' ? input.organisation : '',
    fit: null,
    deadline: event ? null : dayOf(input.deadline),
    ...(event ? { eventDates: { start: dayOf(input.eventStart), end: dayOf(input.eventEnd) } } : {}),
    ...(event || input.deadline ? {} : { noDeadlineText: 'No deadline stated' }),
    detail: {
      ...(typeof input.location === 'string' && input.location ? { location: input.location } : {}),
      reasons: [],
      trust: { state: 'unconfirmed', desktop: PRIVATE_TRUST, phone: PRIVATE_TRUST },
      originalUrl: typeof input.url === 'string' ? input.url : '',
    },
  };
}

/** The extracted fields a manual item shows (what the owner typed, no snippets). */
function ownFields(input: Record<string, unknown>): Record<string, unknown>[] {
  const out: Record<string, unknown>[] = [];
  if (input.organisation) out.push({ name: 'organisation', value: input.organisation });
  if (input.deadline) out.push({ name: 'deadlineAt', value: instant(String(input.deadline), 'end') });
  if (input.eventStart) out.push({ name: 'eventStart', value: instant(String(input.eventStart), 'start') });
  if (input.eventEnd) out.push({ name: 'eventEnd', value: instant(String(input.eventEnd), 'end') });
  if (input.value !== undefined) out.push({ name: 'valueAmount', value: input.value });
  if (input.currency) out.push({ name: 'valueCurrency', value: input.currency });
  if (input.location) out.push({ name: 'location', value: input.location });
  return out;
}

/** Extra keys GET /opportunities/{id} adds for the caller's own item (OwnItem; changes without *_by keys). */
export function ownExtras(s: M4State, id: string): Record<string, unknown> {
  const own = s.own[id];
  if (!own) return {};
  return { fields: ownFields(own.input), changes: own.changes, ownItem: { shareConsent: own.shareConsent, published: own.published } };
}

function opportunity(s: M4State, item: Item): Record<string, unknown> {
  return {
    ...item,
    state: s.states[item.id] ?? 'unseen',
    detail: { ...(item.detail as object), fields: [], sources: [], documents: [], changes: [], note: s.notes[item.id] ?? null, state: s.states[item.id] ?? 'unseen', ...ownExtras(s, item.id) },
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
    if (day(to) - day(from) > 119) return send(res, 422, { detail: 'The calendar shows at most 120 days at a time.' }), true;
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
        const entry: Record<string, unknown> = { id: i.id, stream: i.stream, title: i.title, kind: e.kind, state, provisional: Boolean(i.provisional) };
        if (i.fit) entry.fit = i.fit;
        if (i.organisationShort) entry.organisationShort = i.organisationShort;
        if (CALENDAR_TIMES[i.id] && e.kind === 'deadline') entry.time = CALENDAR_TIMES[i.id];
        byDate.set(e.date, [...(byDate.get(e.date) ?? []), entry]);
      }
    }
    const days = [...byDate.entries()].sort(([a], [c]) => a.localeCompare(c)).map(([date, entries]) => ({ date, entries }));
    return send(res, 200, { days }), true;
  }
  const link = (rotatedAt: string | null) => ({
    url: `https://blackkite.example/api/calendar.ics?token=cal-u1-v${s.feedLinkVersion}`,
    webcalUrl: `webcal://blackkite.example/api/calendar.ics?token=cal-u1-v${s.feedLinkVersion}`,
    rotatedAt,
  });
  const notSetUp = { detail: 'Calendar feeds are not set up on this server yet.' };
  if (method === 'GET' && path === '/calendar/feed-link') {
    if (!s.feedLinkVersion) return send(res, 503, notSetUp), true;
    return send(res, 200, link(s.feedLinkVersion > 1 ? STAMP : null)), true;
  }
  if (method === 'POST' && path === '/calendar/feed-link/rotate') {
    if (!s.feedLinkVersion) return send(res, 503, notSetUp), true;
    s.feedLinkVersion += 1;
    return send(res, 200, link(STAMP)), true;
  }
  if (method === 'POST' && path === '/items') {
    const refused = itemRefusal(b, true, b.stream);
    if (refused.length) return send(res, 422, refusal(refused)), true;
    const id = `own-${Object.keys(s.own).length + 1}`;
    const input = Object.fromEntries(Object.entries(b).filter(([, v]) => v !== null && v !== undefined && v !== ''));
    if (typeof input.currency === 'string') input.currency = input.currency.toUpperCase();
    s.own[id] = { input, shareConsent: false, shareConsentAt: null, published: false, changes: [] };
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
  const isPublic = { detail: "This item is public now, so it can't be changed or deleted here. Ask an admin if something is wrong with it." };
  if (method === 'PUT' && m[2]) {
    if (typeof b.allow !== 'boolean' || Object.keys(b).length !== 1) return send(res, 422, refusal([{ field: 'allow', message: 'true or false' }])), true;
    if (own.published && !b.allow) return send(res, 409, { detail: "This item is public now, so sharing can't be withdrawn. Ask an admin if it should come down." }), true;
    if (b.allow && !own.shareConsent) own.shareConsentAt = STAMP;
    own.shareConsent = b.allow;
    return send(res, 200, { allow: own.shareConsent, published: own.published }), true;
  }
  if ((method === 'PATCH' || method === 'DELETE') && !m[2] && own.published) return send(res, 409, isPublic), true;
  if (method === 'PATCH' && !m[2]) {
    if (b.stream === null || b.title === null) return send(res, 422, refusal([{ field: b.stream === null ? 'stream' : 'title', message: 'cannot be cleared' }])), true;
    const refused = itemRefusal(b, false, b.stream ?? own.input.stream);
    if (refused.length) return send(res, 422, refusal(refused)), true;
    const next = { ...own.input, ...b };
    for (const [k, v] of Object.entries(b)) {
      if (k !== 'notes' && JSON.stringify(own.input[k] ?? null) !== JSON.stringify(v ?? null)) own.changes = [{ field: k, old: own.input[k] ?? null, new: v ?? null, at: STAMP }, ...own.changes];
    }
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
      .filter(([, o]) => !o.published && o.shareConsent)
      .map(([id, o]) => catalogueItem(id, o));
    return send(res, 200, { total: items.length, items }), true;
  }
  const m = p.match(/^\/catalogue\/([^/]+)\/publish$/);
  if (method === 'POST' && m) {
    const id = decodeURIComponent(m[1]!);
    const own = s.own[id];
    if (!own) return send(res, 404, { detail: 'Opportunity not found' }), true;
    if (own.published) return send(res, 200, catalogueItem(id, own)), true;
    if (!own.shareConsent) return send(res, 409, { detail: 'The owner has not agreed to share this item, so it stays private.' }), true;
    own.published = true;
    own.changes = [{ field: 'visibility', old: { visibility: 'private' }, new: { visibility: 'public' }, at: STAMP }, ...own.changes];
    return send(res, 200, catalogueItem(id, own)), true;
  }
  return false;
}

/** CatalogueItem (api routes/catalogue.py) for a manual item: never names the owner. */
function catalogueItem(id: string, o: OwnRecord): Record<string, unknown> {
  const out: Record<string, unknown> = {
    id,
    stream: o.input.stream,
    title: o.input.title,
    organisation: o.input.organisation ?? null,
    status: 'open',
    verification: 'unverified',
    trust: 'unconfirmed',
    needsReview: false,
    reviewReasons: [],
    deadline: o.input.deadline ?? null,
    memberVisible: o.published,
    sources: [],
    createdAt: STAMP,
    updatedAt: STAMP,
    visibility: o.published ? 'public' : 'private',
  };
  if (o.shareConsentAt) out.shareConsentAt = o.shareConsentAt;
  if (o.published) out.madePublicAt = STAMP;
  if (o.input.url) out.url = o.input.url;
  return out;
}
