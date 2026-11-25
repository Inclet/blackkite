import http from 'node:http';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

/**
 * A stub member API (docs/api-contract.md section 2) for the e2e run. One server
 * for the whole run, on BK_E2E_API_PORT (the preview server proxies to it).
 * State is per session: the `bk_stub` cookie names it, so parallel tests do not
 * see each other's saves. No cookie: every member route answers 401.
 *
 * Member routes (sources and source suggestions included) answer only under /api
 * (GET /me and /auth/* keep their paths), and admin routes only under /api/admin
 * (contract section 4), so a client call on an old path fails the run. Source,
 * run, suggestion, user and invite answers are snake_case, as the API's Phase 3
 * models send them; the catalogue is camelCase. Admin routes answer 403 unless
 * the session's role is admin.
 *
 * Control routes for the tests themselves (not proxied, called from Node):
 *   POST /__stub/sessions/:id   body: Partial<Seed>, resets that session
 *   GET  /__stub/sessions/:id/seen   the requests that session made
 *   GET  /__stub/anonymous/seen      requests made without a session cookie
 *
 * POST /api/unsubscribe answers with or without a session (see unsubscribe below).
 */

export const STUB_COOKIE = 'bk_stub';

interface Item {
  id: string;
  stream: string;
  title: string;
  organisation: string;
  fit: string | null;
  deadline: string | null;
  [k: string]: unknown;
}

export interface Seed {
  items: Item[];
  states: Record<string, string>;
  notes: Record<string, string>;
  profiles: Record<string, unknown>[];
  digest: Record<string, unknown>;
  /** The account's name; "" when unset (the feed sends "", GET /me sends null). */
  userName: string;
  /** Each dismiss reason the session sent, by item. */
  dismissReasons: Record<string, string>;
  /** GET /me's role; admin routes answer 403 for "member". */
  role: 'admin' | 'member';
  /** The source registry, as the admin API sends it (api SourceOut, snake_case). */
  sources: Record<string, unknown>[];
  /** Source ids this session muted. */
  mutes: string[];
  /** Every suggestion (api AdminSuggestionOut); members see their own (user_id u1). */
  suggestions: Record<string, unknown>[];
  /** Runs per source, newest first (api RunOut). */
  runs: Record<string, Record<string, unknown>[]>;
  /** Status changes per source, newest first (api StatusChangeOut). */
  history: Record<string, Record<string, unknown>[]>;
  /** The admin catalogue (api CatalogueItem, camelCase). */
  catalogue: Record<string, unknown>[];
  users: Record<string, unknown>[];
  invites: Record<string, unknown>[];
}

export interface Seen {
  method: string;
  url: string;
  contentType: string;
  body: string;
}

const trust = (state: string, text: string) => ({ state, desktop: text, phone: text });

/** Four items in a scrambled order (the screens rank them). Dates read against the frozen 24 Nov 2026. */
export function defaultItems(): Item[] {
  return [
    {
      id: 'tbond-5y',
      provisional: false,
      stream: 'investment',
      title: 'Five-year treasury bond',
      organisation: 'National Bank of Rwanda',
      fit: null,
      note: 'trading on the RSE',
      deadline: null,
      noDeadlineText: 'No deadline',
      detail: { profile: 'Personal', reasons: [], trust: trust('confirmed', 'Listed on the RSE’s own bond table.'), originalUrl: 'https://www.rse.rw/' },
    },
    {
      id: 't2s-call',
      provisional: true,
      stream: 'funding',
      title: 'Transition to Scale research and innovation call',
      organisation: 'National Council for Science and Technology',
      organisationShort: 'NCST',
      fit: 'possible',
      deadline: '2026-12-07',
      detail: {
        profile: 'AI lab',
        location: 'Kigali',
        reasons: ['It funds applied research and innovation, which may cover AI and data work.'],
        trust: trust('confirmed', 'Matched to the call on NCST’s own site.'),
        originalUrl: 'https://www.ncst.gov.rw/',
      },
    },
    {
      id: 'wfp-logistics',
      provisional: false,
      stream: 'tender',
      title: 'Logistics, transport and warehousing support',
      organisation: 'World Food Programme',
      fit: 'strong',
      deadline: '2026-11-30',
      detail: {
        profile: 'Ironji-Trade',
        location: 'Kigali',
        reasons: ['It asks for transport, warehousing and logistics support, which you offer.'],
        toCheck: 'To check: it may require an owned fleet.',
        trust: trust('unconfirmed', 'Found on Job in Rwanda, posted 9 Nov. Check the date on WFP’s own site before you act.'),
        originalUrl: 'https://www.jobinrwanda.com/jobs/tender',
      },
    },
    {
      id: 'abh-summit',
      provisional: false,
      stream: 'event',
      title: 'ABH Summit and Grand Finale',
      organisation: "Africa's Business Heroes",
      fit: null,
      topic: 'Startups and investors',
      venue: 'Kigali Convention Centre',
      deadline: null,
      eventDates: { start: '2026-12-01', end: '2026-12-02' },
      detail: {
        profile: 'Personal',
        location: 'Kigali Convention Centre',
        reasons: ['It is about startups and investors, one of your event topics.'],
        trust: trust('confirmed', 'Dates and venue match the organiser’s own event page.'),
        originalUrl: 'https://africabusinessheroes.org/',
      },
    },
  ];
}

/**
 * The detail extras GET /api/opportunities/{id} adds (api OpportunityOut): fields
 * with a snippet (or snippets, for requirements), sources, documents by name,
 * changes, the note and the state. Real shapes, checked by tests/contract.
 */
export const DETAIL_EXTRAS: Record<string, Record<string, unknown>> = {
  'wfp-logistics': {
    fields: [
      { name: 'organisation', value: 'World Food Programme', snippet: 'The World Food Programme (WFP) invites bids' },
      { name: 'deadlineAt', value: '2026-11-30T17:00:00+02:00', snippet: 'Closing date: 30 November 2026, 17:00 Kigali time' },
      { name: 'valueAmount', value: 120000000, snippet: 'estimated at FRW 120,000,000' },
      { name: 'requirements', value: ['Proof of owned vehicles', 'RRA tax clearance'], snippets: ['logbooks in the bidder’s name', 'a valid tax clearance certificate'] },
      { name: 'location', value: 'Kigali' },
    ],
    sources: [
      {
        name: 'Job in Rwanda, tenders',
        url: 'https://www.jobinrwanda.com/jobs/tender',
        isOriginal: false,
        firstSeen: '2026-11-09T06:00:00Z',
        lastSeen: '2026-11-24T06:00:00Z',
      },
    ],
    documents: [{ name: 'wfp-logistics-rfp.pdf' }],
    changes: [{ field: 'deadline_at', old: '2026-11-28T17:00:00+02:00', new: '2026-11-30T17:00:00+02:00', at: '2026-11-20T06:00:00Z' }],
  },
};

/** One GET /api/opportunities/{id} answer, in the API's shape. */
export function opportunityBody(item: Item & { state: string }, note: string | null): Record<string, unknown> {
  const extras = { fields: [], sources: [], documents: [], changes: [], ...DETAIL_EXTRAS[item.id] };
  return { ...item, detail: { ...(item.detail as object), ...extras, note, state: item.state } };
}

export function defaultSeed(): Seed {
  return {
    items: defaultItems(),
    states: {},
    notes: {},
    profiles: [
      {
        id: 'p1',
        name: 'Ironji-Trade',
        type: 'business',
        version: 1,
        active: true,
        createdAt: '2026-11-01T08:00:00Z',
        updatedAt: '2026-11-01T08:00:00Z',
        data: {
          streams: ['tender', 'funding', 'event'],
          location: 'Kigali, Rwanda',
          services: ['dry freight', 'cold chain', 'last-mile distribution'],
          registrationsHeld: ['RDB company registration', 'RRA tax clearance', 'RSSB clearance'],
          registrationsNotHeld: ['Umucyo supplier account', 'transport operator licence'],
          capacity: { model: 'partner network', trucksInNetwork: 1000, refrigeratedInNetwork: 100, ownedTrucks: null, tonnage: null },
          minContractRwf: 5000000,
        },
      },
      {
        id: 'p3',
        name: 'Personal',
        type: 'personal',
        version: 1,
        active: true,
        createdAt: '2026-11-01T08:00:00Z',
        updatedAt: '2026-11-01T08:00:00Z',
        data: { streams: ['investment', 'event'], instruments: ['treasury bonds and bills', 'RSE shares'], eventTopics: ['AI and tech'], ticketRangeRwf: null },
      },
    ],
    // GET /api/digest-settings never sends an address (the account email is GET /me's).
    digest: { channel: 'email', frequency: 'weekly', day: 'mon', alertMinFit: 'strong', streams: null },
    userName: 'Clet',
    dismissReasons: {},
    role: 'admin',
    sources: defaultSources(),
    mutes: [],
    suggestions: [
      {
        id: 'sg-1',
        userId: 'u2',
        url: 'https://www.rdb.rw/calls',
        note: 'Covers: RDB calls for proposals\nWhy it is useful: funding calls appear here first',
        status: 'suggested',
        createdAt: '2026-11-23T08:00:00Z',
        reviewedAt: null,
        reviewedBy: null,
        sourceId: null,
      },
    ],
    runs: {
      'src-umucyo': [
        { id: 'run-2', startedAt: '2026-11-24T04:00:00Z', finishedAt: '2026-11-24T04:01:00Z', status: 'succeeded', itemsFound: 9, itemsNew: 2, itemsFailed: 0, error: null },
        { id: 'run-1', startedAt: '2026-11-23T22:00:00Z', finishedAt: '2026-11-23T22:00:30Z', status: 'failed', itemsFound: 0, itemsNew: 0, itemsFailed: 0, error: 'HTTP 503 from www.umucyo.gov.rw' },
      ],
    },
    history: {
      'src-umucyo': [{ at: '2026-11-20T08:00:00Z', oldStatus: null, newStatus: 'testing', changedBy: 'u1', reason: 'created' }],
    },
    catalogue: [
      {
        id: 'op-warehouse',
        stream: 'tender',
        title: 'Construction of a cold-storage warehouse',
        organisation: 'MINAGRI',
        status: 'open',
        verification: 'unverified',
        trust: 'conflict',
        needsReview: true,
        reviewReasons: [{ code: 'deadline_conflict', detail: 'Job in Rwanda says 3 Dec 2026; The New Times says 10 Dec 2026.' }],
        deadline: '2026-12-03',
        memberVisible: true,
        sources: [{ name: 'Job in Rwanda, tenders', status: 'active', kind: 'publisher', isOriginal: false, url: 'https://www.jobinrwanda.com/jobs/tender' }],
        createdAt: '2026-11-22T08:00:00Z',
        updatedAt: '2026-11-22T08:00:00Z',
      },
    ],
    users: [
      { id: 'u1', email: 'clet@example.rw', name: 'Clet', role: 'admin', status: 'active', createdAt: '2026-11-01T08:00:00Z', lastSignInAt: '2026-11-24T07:00:00Z' },
      { id: 'u2', email: 'amina@example.rw', name: 'Amina', role: 'member', status: 'active', createdAt: '2026-11-10T08:00:00Z', lastSignInAt: null },
    ],
    invites: [],
  };
}

const STAMP_SOURCE = '2026-11-20T08:00:00Z';

/** One SourceOut (api routes/source_schemas.py), camelCase. */
export function stubSource(over: Record<string, unknown>): Record<string, unknown> {
  return {
    id: 'src-x',
    name: 'Source',
    homeUrl: 'https://example.rw/',
    publisher: null,
    streams: ['tender'],
    kind: 'publisher',
    collectorType: 'html_list',
    config: {},
    schedule: null,
    effectiveSchedule: '0 */6 * * *',
    rateLimit: null,
    accessNote: null,
    status: 'testing',
    addedBy: 'u1',
    createdAt: STAMP_SOURCE,
    updatedAt: STAMP_SOURCE,
    configChangedAt: null,
    health: 'unknown',
    lastSuccessAt: null,
    lastRunAt: null,
    items30d: 0,
    promotionRuns: 0,
    ...over,
  };
}

export function defaultSources(): Record<string, unknown>[] {
  return [
    stubSource({
      id: 'src-jir',
      name: 'Job in Rwanda, tenders',
      homeUrl: 'https://www.jobinrwanda.com/jobs/tender',
      publisher: 'Job in Rwanda',
      kind: 'publisher',
      config: { list_url: 'https://www.jobinrwanda.com/jobs/tender', selectors: { item: 'article', title: 'h2 a' } },
      status: 'active',
      health: 'ok',
      lastSuccessAt: '2026-11-24T04:00:00Z',
      lastRunAt: '2026-11-24T04:00:00Z',
      items30d: 31,
      promotionRuns: 5,
    }),
    stubSource({
      id: 'src-rse',
      name: 'RSE bond market',
      homeUrl: 'https://www.rse.rw/',
      publisher: 'Rwanda Stock Exchange',
      kind: 'original',
      streams: ['investment'],
      config: { list_url: 'https://www.rse.rw/bonds', selectors: { item: 'tr', title: 'td' } },
      status: 'active',
      health: 'degraded',
      lastSuccessAt: '2026-11-23T04:00:00Z',
      lastRunAt: '2026-11-24T04:00:00Z',
      items30d: 4,
      promotionRuns: 3,
    }),
    stubSource({
      id: 'src-umucyo',
      name: 'Umucyo e-procurement',
      homeUrl: 'https://www.umucyo.gov.rw/',
      publisher: 'Rwanda Public Procurement Authority',
      kind: 'original',
      config: { list_url: 'https://www.umucyo.gov.rw/tenders', selectors: { item: 'tr', title: 'td a' } },
      accessNote: 'Tested from the host 24 Nov 2026: plain fetch works at a low rate.',
      status: 'testing',
      health: 'degraded',
      lastSuccessAt: '2026-11-24T04:00:00Z',
      lastRunAt: '2026-11-24T04:00:00Z',
      items30d: 9,
      configChangedAt: '2026-11-22T08:00:00Z',
      promotionRuns: 1,
    }),
  ];
}

/** GET /api/admin/collector-types, the real API answer (tests/fixtures/collector-types.json, dumped from api CollectorTypeOut by alias). */
export const COLLECTOR_TYPES: unknown = JSON.parse(readFileSync(fileURLToPath(new URL('../fixtures/collector-types.json', import.meta.url)), 'utf8'));

const SOURCE_KEYS = new Set(['name', 'homeUrl', 'publisher', 'streams', 'kind', 'collectorType', 'config', 'schedule', 'rateLimit', 'accessNote']);
const STATUS_MOVES: Record<string, string[]> = {
  suggested: ['testing', 'retired'],
  testing: ['active', 'paused', 'retired'],
  active: ['paused', 'retired', 'testing'],
  paused: ['active', 'testing', 'retired'],
  retired: ['testing'],
};

/** Like SourceIn / SourcePatch: unknown keys, missing required ones, an original search_query and bad URLs are refused. */
function sourceRefusal(b: Record<string, unknown>, create: boolean): string | null {
  const extra = Object.keys(b).filter((k) => !SOURCE_KEYS.has(k) && !(create && k === 'suggestionId'));
  if (extra.length) return `extra keys: ${extra.join(', ')}`;
  if (create) {
    for (const k of ['name', 'homeUrl', 'streams', 'kind', 'collectorType']) if (b[k] === undefined || b[k] === null || b[k] === '') return `${k}: required`;
  }
  if (b.homeUrl !== undefined && !/^https?:\/\/[^/]+\.[^/]+/.test(String(b.homeUrl))) return 'homeUrl: not a public web address';
  if (Array.isArray(b.streams) && b.streams.length === 0) return 'streams: at least one';
  if (b.kind === 'original' && b.collectorType === 'search_query') return "a search_query source cannot be kind 'original'";
  if (b.config !== undefined && (b.config === null || typeof b.config !== 'object' || Array.isArray(b.config))) return 'config must be a JSON object';
  return null;
}

/** POST …/test-run: a config whose first URL contains "fail" fails; anything else parses two items. */
function preview(config: Record<string, unknown>): Record<string, unknown> {
  const url = String(config.list_url ?? config.feed_url ?? config.endpoint ?? '');
  if (url.includes('fail')) {
    return { ok: false, error: `HTTP 403 from ${url.replace(/^https?:\/\//, '').split('/')[0]}`, items: [], totalParsed: 0, requestsMade: 1, elapsedSeconds: 0.4 };
  }
  return {
    ok: true,
    error: null,
    items: [
      {
        url: 'https://www.ncst.gov.rw/calls/1',
        title: 'Call for applied research proposals',
        organisation: 'National Council for Science and Technology',
        listedPublished: '20 Nov 2026',
        listedDeadline: '15 Dec 2026',
        snippet: 'Grants for applied research and innovation.',
        detailUrl: null,
        extra: {},
      },
      {
        url: 'https://www.ncst.gov.rw/calls/2',
        title: 'Innovation challenge 2027',
        organisation: null,
        listedPublished: null,
        listedDeadline: '31 Jan 2027',
        snippet: null,
        detailUrl: null,
        extra: {},
      },
    ],
    totalParsed: 2,
    requestsMade: 1,
    elapsedSeconds: 0.8,
  };
}

interface Session extends Seed {
  seen: Seen[];
}

function cookie(req: http.IncomingMessage, name: string): string | undefined {
  for (const part of (req.headers.cookie ?? '').split(';')) {
    const [k, ...v] = part.trim().split('=');
    if (k === name) return decodeURIComponent(v.join('='));
  }
  return undefined;
}

function send(res: http.ServerResponse, status: number, body?: unknown): void {
  if (body === undefined) {
    res.writeHead(status).end();
    return;
  }
  res.writeHead(status, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(body));
}

/** Like the API (member/profiles.py): data keys outside the type's model, or no streams, are refused. */
const COMMON_KEYS = ['streams', 'location', 'locations', 'exclusions', 'provisional'];
const PROFILE_KEYS: Record<string, Set<string>> = {
  business: new Set([...COMMON_KEYS, 'services', 'sectors', 'capacity', 'registrationsHeld', 'registrationsNotHeld', 'minContractRwf']),
  personal: new Set([...COMMON_KEYS, 'instruments', 'ticketRangeRwf', 'horizon', 'eventTopics', 'availability', 'budgetRwf']),
};
const PROFILE_BODY_KEYS = new Set(['name', 'type', 'data', 'active']);

function profileRefusal(body: unknown, currentType: string | undefined): string | null {
  const b = (body ?? {}) as Record<string, unknown>;
  const extra = Object.keys(b).filter((k) => !PROFILE_BODY_KEYS.has(k));
  if (extra.length) return `extra keys: ${extra.join(', ')}`;
  const type = (b.type as string | undefined) ?? currentType;
  if (!type || !PROFILE_KEYS[type]) return 'type';
  if (b.data === undefined) return currentType && b.type && b.type !== currentType ? 'changing the type needs new data for that type' : null;
  const data = b.data as Record<string, unknown>;
  const bad = Object.keys(data).filter((k) => !PROFILE_KEYS[type]!.has(k));
  if (bad.length) return `data: extra keys for ${type}: ${bad.join(', ')}`;
  if (!Array.isArray(data.streams) || data.streams.length === 0) return 'data.streams: at least one';
  return null;
}

/** The time the stub stamps on profiles (the run's frozen now). */
const STAMP = '2026-11-24T08:00:00Z';

const DIGEST_KEYS = new Set(['channel', 'frequency', 'day', 'alertMinFit', 'streams']);
const ALERT_MIN_FIT = new Set(['strong', 'good', null]);

/** Like the API's StateIn: only these dismiss reason codes. */
const DISMISS_REASONS = new Set(['not_my_sector', 'too_small', 'cant_meet_requirements', 'already_knew', 'other']);

const STATES = new Set(['saved', 'dismissed', 'acting', 'done', 'unseen']);

function sortSoonest(items: Item[]): Item[] {
  const date = (i: Item) => i.deadline ?? (i.eventDates as { start?: string } | undefined)?.start ?? '9999';
  return [...items].sort((a, b) => date(a).localeCompare(date(b)));
}

/** Handle one member-API request for a session. */
function member(s: Session, method: string, fullPath: string, body: unknown, res: http.ServerResponse, url = fullPath): void {
  // Earlier routes keep their paths; every other member route is under /api (contract section 2).
  if (method === 'GET' && fullPath === '/me') {
    return send(res, 200, { id: 'u1', email: 'clet@example.rw', name: s.userName || null, role: s.role, status: 'active', created_at: '2026-11-01T08:00:00Z' });
  }
  if (method === 'POST' && fullPath === '/auth/logout') return send(res, 204);
  if (!fullPath.startsWith('/api/')) return send(res, 404, { detail: 'Not found' });
  const path = fullPath.slice('/api'.length);
  // Every feed, shortlist and detail item carries the caller's state (contract section 2).
  const withState = (i: Item) => ({ ...i, state: s.states[i.id] ?? 'unseen' });
  const opp = path.match(/^\/opportunities\/([^/]+)(\/state|\/note)?$/);
  const prof = path.match(/^\/profiles\/([^/]+)$/);

  if (path.startsWith('/admin/') || path === '/admin') return admin(s, method, path, url, body, res);
  const mute = path.match(/^\/sources\/([^/]+)\/mute$/);
  if (method === 'GET' && path === '/sources') {
    return send(
      res,
      200,
      s.sources
        .filter((x) => x.status === 'active')
        .map((x) => ({
          id: x.id,
          name: x.name,
          homeUrl: x.homeUrl,
          publisher: x.publisher,
          kind: x.kind,
          streams: x.streams,
          lastSuccessAt: x.lastSuccessAt,
          items30d: x.items30d,
          health: x.health,
          muted: s.mutes.includes(String(x.id)),
        })),
    );
  }
  if (mute) {
    const id = decodeURIComponent(mute[1]!);
    if (method === 'POST') {
      if (!s.sources.some((x) => x.id === id && x.status === 'active')) return send(res, 404, { detail: 'Source not found' });
      if (!s.mutes.includes(id)) s.mutes.push(id);
      return send(res, 204);
    }
    if (method === 'DELETE') {
      s.mutes = s.mutes.filter((m) => m !== id);
      return send(res, 204);
    }
  }
  if (path === '/source-suggestions') {
    if (method === 'GET') {
      return send(
        res,
        200,
        s.suggestions.filter((x) => x.userId === 'u1').map(({ userId: _u, reviewedBy: _r, ...x }) => x),
      );
    }
    if (method === 'POST') {
      const b = (body ?? {}) as Record<string, unknown>;
      const extra = Object.keys(b).filter((k) => k !== 'url' && k !== 'note');
      if (extra.length) return send(res, 422, { detail: `extra keys: ${extra.join(', ')}` });
      if (typeof b.url !== 'string' || !/^https?:\/\/[^/]+\.[^/]+/.test(b.url)) return send(res, 422, { detail: 'url: not a public web address' });
      if (b.note !== undefined && b.note !== null && (typeof b.note !== 'string' || b.note.length > 2000)) return send(res, 422, { detail: 'note' });
      const row = { id: `sg-${s.suggestions.length + 10}`, userId: 'u1', url: b.url, note: b.note ?? null, status: 'suggested', createdAt: STAMP, reviewedAt: null, reviewedBy: null, sourceId: null };
      s.suggestions.push(row);
      const { userId: _u, reviewedBy: _r, ...out } = row;
      return send(res, 201, out);
    }
  }
  if (method === 'DELETE' && path === '/me') return send(res, 204);
  if (method === 'GET' && path === '/me/export') return send(res, 200, { profiles: s.profiles, digest: s.digest, states: s.states, notes: s.notes });
  if (method === 'GET' && path === '/feed') {
    // Deliberately not in closing order: the web app ranks what it gets.
    const items = s.items.filter((i) => s.states[i.id] !== 'dismissed').map(withState);
    return send(res, 200, { user: { name: s.userName }, sources: { checked: 3, when: 'this morning' }, digest: { channel: 'email' }, items });
  }
  if (method === 'GET' && path === '/shortlist') {
    return send(res, 200, sortSoonest(s.items.filter((i) => s.states[i.id] === 'saved' || s.states[i.id] === 'acting').map(withState)));
  }
  if (opp) {
    const item = s.items.find((i) => i.id === decodeURIComponent(opp[1]!));
    if (!item) return send(res, 404, { detail: 'Not found' });
    if (method === 'GET' && !opp[2]) {
      return send(res, 200, opportunityBody(withState(item), s.notes[item.id] ?? null));
    }
    if (method === 'PUT' && opp[2] === '/state') {
      const b = (body ?? {}) as { state?: string; dismissReason?: unknown };
      const state = b.state;
      if (!state || !STATES.has(state)) return send(res, 422, { detail: 'Unknown state' });
      const extra = Object.keys(b).filter((k) => k !== 'state' && k !== 'dismissReason');
      if (extra.length) return send(res, 422, { detail: `extra keys: ${extra.join(', ')}` });
      if (b.dismissReason !== undefined && b.dismissReason !== null && !DISMISS_REASONS.has(b.dismissReason as string)) {
        return send(res, 422, { detail: 'dismissReason' });
      }
      s.states[item.id] = state;
      if (state === 'dismissed' && typeof b.dismissReason === 'string') s.dismissReasons[item.id] = b.dismissReason;
      else delete s.dismissReasons[item.id];
      return send(res, 200, { state });
    }
    if (method === 'PUT' && opp[2] === '/note') {
      s.notes[item.id] = String((body as { note?: unknown } | null)?.note ?? '');
      return send(res, 200, { note: s.notes[item.id] });
    }
  }
  if (method === 'GET' && path === '/profiles') return send(res, 200, s.profiles);
  if (method === 'POST' && path === '/profiles') {
    const refused = profileRefusal(body, undefined);
    if (refused) return send(res, 422, { detail: refused });
    const p = { id: `p${s.profiles.length + 10}`, version: 1, active: true, ...(body as object), createdAt: STAMP, updatedAt: STAMP };
    s.profiles.push(p);
    return send(res, 201, p);
  }
  if (prof) {
    const i = s.profiles.findIndex((p) => p.id === prof[1]);
    if (i < 0) return send(res, 404, { detail: 'Not found' });
    if (method === 'PATCH') {
      const before = s.profiles[i]!;
      const refused = profileRefusal(body, before.type as string);
      if (refused) return send(res, 422, { detail: refused });
      s.profiles[i] = { ...before, ...(body as object), version: Number(before.version) + 1, updatedAt: STAMP };
      return send(res, 200, s.profiles[i]);
    }
    if (method === 'DELETE') {
      s.profiles.splice(i, 1);
      return send(res, 204);
    }
  }
  if (path === '/digest-settings') {
    if (method === 'GET') return send(res, 200, s.digest);
    if (method === 'PUT') {
      const b = body as Record<string, unknown>;
      // Like the API: unknown keys are refused.
      const unknown = Object.keys(b ?? {}).filter((k) => !DIGEST_KEYS.has(k));
      if (unknown.length) return send(res, 422, { detail: `extra keys: ${unknown.join(', ')}` });
      if (b.frequency !== 'weekly' && b.frequency !== 'off') return send(res, 422, { detail: 'frequency' });
      if ('alertMinFit' in b && !ALERT_MIN_FIT.has(b.alertMinFit as string | null)) return send(res, 422, { detail: 'alertMinFit' });
      s.digest = { ...s.digest, ...b, day: 'mon', channel: 'email' };
      return send(res, 200, s.digest);
    }
  }
  return send(res, 404, { detail: 'Not found' });
}

/** SourceDetailOut: the SourceOut plus the promotion gate and the status history. */
function detail(s: Session, row: Record<string, unknown>): Record<string, unknown> {
  const goodRuns = Number(row.promotionRuns);
  return {
    ...row,
    promotionGate: { goodRuns, needed: 2, since: row.configChangedAt ?? null, met: goodRuns >= 2 },
    statusHistory: s.history[String(row.id)] ?? [],
  };
}

function logStatus(s: Session, id: string, oldStatus: unknown, newStatus: unknown, reason: string | null): void {
  s.history[id] = [{ at: STAMP, oldStatus: oldStatus ?? null, newStatus, changedBy: 'u1', reason }, ...(s.history[id] ?? [])];
}

const activeAdmins = (s: Session) => s.users.filter((u) => u.role === 'admin' && u.status === 'active').length;

/** The admin API (contract section 4.1), under /api/admin. 403 unless the session is an admin. */
function admin(s: Session, method: string, path: string, fullPath: string, body: unknown, res: http.ServerResponse): void {
  if (s.role !== 'admin') return send(res, 403, { detail: 'Admins only' });
  const query = new URLSearchParams(fullPath.split('?')[1] ?? '');
  const p = path.slice('/admin'.length);
  const b = (body ?? {}) as Record<string, unknown>;
  const src = p.match(/^\/sources\/([^/]+)(\/status|\/runs|\/test-run)?$/);
  const sug = p.match(/^\/source-suggestions\/([^/]+)\/(accept|reject)$/);
  const review = p.match(/^\/catalogue\/([^/]+)\/review$/);
  const deactivate = p.match(/^\/users\/([^/]+)\/deactivate$/);
  const user = p.match(/^\/users\/([^/]+)$/);
  const invite = p.match(/^\/invites\/([^/]+)$/);

  if (method === 'GET' && p === '/collector-types') return send(res, 200, COLLECTOR_TYPES);
  if (method === 'GET' && p === '/sources') {
    const status = query.get('status');
    return send(res, 200, [...s.sources].filter((x) => !status || x.status === status).sort((a, c) => String(a.name).localeCompare(String(c.name))));
  }
  if (method === 'POST' && p === '/sources') {
    const refused = sourceRefusal(b, true);
    if (refused) return send(res, 422, { detail: refused });
    if (s.sources.some((x) => x.name === b.name)) return send(res, 409, { detail: 'A source with that name already exists' });
    const suggestionId = b.suggestionId as string | undefined;
    if (suggestionId !== undefined) {
      const sg = s.suggestions.find((x) => x.id === suggestionId);
      if (!sg) return send(res, 404, { detail: 'Suggestion not found' });
      if (sg.status !== 'accepted' || sg.sourceId) return send(res, 409, { detail: 'Suggestion must be accepted and not yet used' });
    }
    const { suggestionId: _s, ...fields } = b;
    const row = stubSource({ ...fields, id: `src-${s.sources.length + 10}`, status: 'testing', createdAt: STAMP, updatedAt: STAMP, configChangedAt: STAMP });
    s.sources.push(row);
    logStatus(s, String(row.id), null, 'testing', 'created');
    if (suggestionId) s.suggestions = s.suggestions.map((x) => (x.id === suggestionId ? { ...x, sourceId: row.id } : x));
    return send(res, 201, detail(s, row));
  }
  if (method === 'POST' && p === '/sources/test-run') {
    if (typeof b.collectorType !== 'string' || !b.config || typeof b.config !== 'object') return send(res, 422, { detail: 'collectorType and config are required' });
    return send(res, 200, preview(b.config as Record<string, unknown>));
  }
  if (src) {
    const id = decodeURIComponent(src[1]!);
    const i = s.sources.findIndex((x) => x.id === id);
    if (i < 0) return send(res, 404, { detail: 'Source not found' });
    const row = s.sources[i]!;
    if (method === 'GET' && !src[2]) return send(res, 200, detail(s, row));
    if (method === 'GET' && src[2] === '/runs') {
      const status = query.get('status');
      const all = (s.runs[id] ?? []).filter((r) => !status || r.status === status);
      const offset = Number(query.get('offset') ?? 0);
      const limit = Number(query.get('limit') ?? 50);
      return send(res, 200, { total: all.length, items: all.slice(offset, offset + limit) });
    }
    if (method === 'POST' && src[2] === '/test-run') return send(res, 200, preview(row.config as Record<string, unknown>));
    if (method === 'PATCH' && !src[2]) {
      const refused = sourceRefusal({ kind: row.kind, collectorType: row.collectorType, ...b }, false);
      if (refused) return send(res, 422, { detail: refused });
      if (b.name !== undefined && s.sources.some((x) => x.name === b.name && x.id !== id)) return send(res, 409, { detail: 'A source with that name already exists' });
      const configChanged =
        (b.collectorType !== undefined && b.collectorType !== row.collectorType) || (b.config !== undefined && JSON.stringify(b.config) !== JSON.stringify(row.config));
      const next: Record<string, unknown> = { ...row, ...b, updatedAt: STAMP };
      if (configChanged) Object.assign(next, { configChangedAt: STAMP, promotionRuns: 0, status: row.status === 'active' ? 'testing' : row.status });
      if (next.status !== row.status) logStatus(s, id, row.status, next.status, 'config changed');
      s.sources[i] = next;
      return send(res, 200, detail(s, next));
    }
    if (method === 'POST' && src[2] === '/status') {
      const to = String(b.status ?? '');
      if (to === row.status) return send(res, 200, detail(s, row));
      if (!(STATUS_MOVES[String(row.status)] ?? []).includes(to)) return send(res, 409, { detail: `cannot move a source from ${row.status} to ${to}` });
      if (to === 'active' && Number(row.promotionRuns) < 2) {
        return send(res, 409, { detail: `needs 2 successful runs that found items since its config last changed; has ${row.promotionRuns}` });
      }
      s.sources[i] = { ...row, status: to, updatedAt: STAMP };
      logStatus(s, id, row.status, to, null);
      return send(res, 200, detail(s, s.sources[i]!));
    }
  }
  if (method === 'GET' && p === '/source-suggestions') {
    const status = query.has('status') ? query.get('status') : 'suggested';
    return send(res, 200, s.suggestions.filter((x) => !status || x.status === status));
  }
  if (method === 'POST' && sug) {
    const i = s.suggestions.findIndex((x) => x.id === decodeURIComponent(sug[1]!));
    if (i < 0) return send(res, 404, { detail: 'Suggestion not found' });
    if (s.suggestions[i]!.status !== 'suggested') return send(res, 409, { detail: `suggestion already ${s.suggestions[i]!.status}` });
    s.suggestions[i] = { ...s.suggestions[i]!, status: sug[2] === 'accept' ? 'accepted' : 'rejected', reviewedAt: STAMP, reviewedBy: 'u1' };
    return send(res, 200, s.suggestions[i]);
  }
  if (method === 'GET' && p === '/catalogue') {
    const nr = query.get('needsReview');
    const items = s.catalogue.filter((x) => nr === null || String(x.needsReview) === nr);
    return send(res, 200, { total: items.length, items });
  }
  if (method === 'POST' && review) {
    const i = s.catalogue.findIndex((x) => x.id === decodeURIComponent(review[1]!));
    if (i < 0) return send(res, 404, { detail: 'Opportunity not found' });
    s.catalogue[i] = { ...s.catalogue[i]!, needsReview: false, reviewReasons: [] };
    return send(res, 200, s.catalogue[i]);
  }
  if (method === 'GET' && p === '/users') return send(res, 200, s.users);
  if (method === 'POST' && deactivate) {
    const id = decodeURIComponent(deactivate[1]!);
    if (id === 'u1') return send(res, 400, { detail: 'You cannot deactivate yourself' });
    const i = s.users.findIndex((x) => x.id === id);
    if (i < 0) return send(res, 404, { detail: 'User not found' });
    if (s.users[i]!.role === 'admin' && s.users[i]!.status === 'active' && activeAdmins(s) <= 1) return send(res, 409, { detail: 'That would leave no active admin' });
    s.users[i] = { ...s.users[i]!, status: 'deactivated' };
    return send(res, 200, s.users[i]);
  }
  if (method === 'PATCH' && user) {
    const id = decodeURIComponent(user[1]!);
    const extra = Object.keys(b).filter((k) => k !== 'role');
    if (extra.length || (b.role !== 'member' && b.role !== 'admin')) return send(res, 422, { detail: 'role: member or admin' });
    if (id === 'u1') return send(res, 400, { detail: 'You cannot change your own role' });
    const i = s.users.findIndex((x) => x.id === id);
    if (i < 0) return send(res, 404, { detail: 'User not found' });
    if (b.role === 'member' && s.users[i]!.role === 'admin' && activeAdmins(s) <= 1) return send(res, 409, { detail: 'That would leave no active admin' });
    s.users[i] = { ...s.users[i]!, role: b.role };
    return send(res, 200, s.users[i]);
  }
  if (p === '/invites') {
    if (method === 'GET') return send(res, 200, s.invites.filter((x) => !query.get('status') || x.status === query.get('status')));
    if (method === 'POST') {
      const email = typeof b.email === 'string' ? b.email.trim().toLowerCase() : '';
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return send(res, 422, { detail: 'email' });
      if (s.users.some((u) => u.email === email)) return send(res, 409, { detail: 'That address already has an account' });
      const row = { id: `inv-${s.invites.length + 1}`, email, invitedBy: 'u1', createdAt: STAMP, expiresAt: '2026-12-01T08:00:00Z', acceptedAt: null, status: 'pending' };
      s.invites = [row, ...s.invites];
      return send(res, 201, row);
    }
  }
  if (method === 'DELETE' && invite) {
    const i = s.invites.findIndex((x) => x.id === decodeURIComponent(invite[1]!));
    if (i < 0) return send(res, 404, { detail: 'Invite not found' });
    s.invites.splice(i, 1);
    return send(res, 204);
  }
  return send(res, 404, { detail: 'Not found' });
}

/**
 * Test tokens for POST /api/unsubscribe: `digest-…` and `alert-…` succeed (and, when
 * the request carries a session cookie, turn that session's digest or alerts off, as
 * the API does for the token's user); `busy` answers 429; anything else 400.
 */
export const UNSUBSCRIBE_INVALID = 'This unsubscribe link is not valid. Change your emails in settings.';

function unsubscribe(method: string, contentType: string, body: unknown, s: Session | undefined, res: http.ServerResponse): void {
  if (method === 'GET') return send(res, 405, { detail: 'Use POST to unsubscribe. Opening this link changes nothing.' });
  if (method !== 'POST') return send(res, 405, { detail: 'Method Not Allowed' });
  if (!contentType.toLowerCase().startsWith('application/json')) return send(res, 415, { detail: 'Send JSON {token} or the one-click form.' });
  const token = (body as { token?: unknown } | null)?.token;
  if (typeof token !== 'string') return send(res, 422, { detail: 'token is required.' });
  if (token === 'busy') return send(res, 429, { detail: 'Too many requests. Try again later.' });
  const kind = token.startsWith('digest-') ? 'digest' : token.startsWith('alert-') ? 'alert' : null;
  if (!kind) return send(res, 400, { detail: UNSUBSCRIBE_INVALID });
  if (s) s.digest = kind === 'digest' ? { ...s.digest, frequency: 'off' } : { ...s.digest, alertMinFit: null };
  return send(res, 200, { kind, detail: "You won't get these emails any more." });
}

export function startStubApi(port: number): Promise<{ port: number; close: () => Promise<void> }> {
  const sessions = new Map<string, Session>();
  const anonymous: Seen[] = [];
  const session = (id: string) => {
    let s = sessions.get(id);
    if (!s) sessions.set(id, (s = { ...defaultSeed(), seen: [] }));
    return s;
  };

  const server = http.createServer((req, res) => {
    let raw = '';
    req.on('data', (c: Buffer) => (raw += c.toString()));
    req.on('end', () => {
      const url = req.url ?? '';
      const path = url.split('?')[0]!;
      const method = req.method ?? 'GET';
      let body: unknown;
      try {
        body = raw ? JSON.parse(raw) : undefined;
      } catch {
        return send(res, 400, { detail: 'Not JSON' });
      }

      const control = path.match(/^\/__stub\/sessions\/([^/]+)(\/seen)?$/);
      if (control) {
        const id = decodeURIComponent(control[1]!);
        if (method === 'POST' && !control[2]) {
          sessions.set(id, { ...defaultSeed(), ...(body as Partial<Seed>), seen: [] });
          return send(res, 204);
        }
        if (method === 'GET' && control[2]) return send(res, 200, session(id).seen);
      }
      if (method === 'GET' && path === '/__stub/anonymous/seen') return send(res, 200, anonymous);

      const seen: Seen = { method, url, contentType: req.headers['content-type'] ?? '', body: raw };
      const id = cookie(req, STUB_COOKIE);
      (id ? session(id).seen : anonymous).push(seen);

      // Sign-in routes work without a session.
      if (method === 'POST' && path === '/auth/request-link') {
        const email = (body as { email?: unknown } | null)?.email;
        if (typeof email !== 'string' || !email.includes('@')) return send(res, 422, { detail: 'email' });
        return send(res, 202, { detail: 'If this address can sign in, a link is on its way.' });
      }
      if (method === 'POST' && path === '/auth/verify') return send(res, 200, { redirect: '/shortlist' });
      // One-click unsubscribe (decision 43) needs no session: the token is the authority.
      if (path === '/api/unsubscribe') return unsubscribe(method, req.headers['content-type'] ?? '', body, id ? session(id) : undefined, res);
      if (!id) return send(res, 401, { detail: 'Sign in first.' });
      member(session(id), method, path, body, res, url);
    });
  });
  return new Promise((resolve, reject) => {
    server.on('error', reject);
    server.listen(port, '127.0.0.1', () =>
      resolve({ port: (server.address() as { port: number }).port, close: () => new Promise((r) => server.close(() => r())) }),
    );
  });
}
