import http from 'node:http';

/**
 * A stub member API (docs/api-contract.md section 2) for the e2e run. One server
 * for the whole run, on BK_E2E_API_PORT (the preview server proxies to it).
 * State is per session: the `bk_stub` cookie names it, so parallel tests do not
 * see each other's saves. No cookie: every member route answers 401.
 *
 * Member routes (sources and source suggestions included) answer only under /api
 * (GET /me and /auth/* keep their paths), so a
 * client call on an old path fails the run.
 *
 * Control routes for the tests themselves (not proxied, called from Node):
 *   POST /__stub/sessions/:id   body: Partial<Seed>, resets that session
 *   GET  /__stub/sessions/:id/seen   the requests that session made
 *   GET  /__stub/anonymous/seen      requests made without a session cookie
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
        data: { streams: ['investment', 'event'], instruments: ['treasury bonds and bills', 'RSE shares'], eventTopics: ['AI and tech'], ticketRangeRwf: null },
      },
    ],
    // GET /api/digest-settings never sends an address (the account email is GET /me's).
    digest: { channel: 'email', frequency: 'weekly', day: 'mon', alertThreshold: 70, streams: null },
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

const DIGEST_KEYS = new Set(['channel', 'frequency', 'day', 'alertThreshold', 'streams']);

const STATES = new Set(['saved', 'dismissed', 'acting', 'done', 'unseen']);

function sortSoonest(items: Item[]): Item[] {
  const date = (i: Item) => i.deadline ?? (i.eventDates as { start?: string } | undefined)?.start ?? '9999';
  return [...items].sort((a, b) => date(a).localeCompare(date(b)));
}

/** Handle one member-API request for a session. */
function member(s: Session, method: string, fullPath: string, body: unknown, res: http.ServerResponse): void {
  // Earlier routes keep their paths; every other member route is under /api (contract section 2).
  if (method === 'GET' && fullPath === '/me') return send(res, 200, { id: 'u1', email: 'clet@example.rw', name: 'Clet', role: 'admin', status: 'active' });
  if (method === 'POST' && fullPath === '/auth/logout') return send(res, 204);
  if (!fullPath.startsWith('/api/')) return send(res, 404, { detail: 'Not found' });
  const path = fullPath.slice('/api'.length);
  // Every feed, shortlist and detail item carries the caller's state (contract section 2).
  const withState = (i: Item) => ({ ...i, state: s.states[i.id] ?? 'unseen' });
  const opp = path.match(/^\/opportunities\/([^/]+)(\/state|\/note)?$/);
  const prof = path.match(/^\/profiles\/([^/]+)$/);

  if (method === 'DELETE' && path === '/me') return send(res, 204);
  if (method === 'GET' && path === '/me/export') return send(res, 200, { profiles: s.profiles, digest: s.digest, states: s.states, notes: s.notes });
  if (method === 'GET' && path === '/feed') {
    // Deliberately not in closing order: the web app ranks what it gets.
    const items = s.items.filter((i) => s.states[i.id] !== 'dismissed').map(withState);
    return send(res, 200, { user: { name: 'Clet' }, sources: { checked: 3, when: 'this morning' }, digest: { channel: 'email' }, items });
  }
  if (method === 'GET' && path === '/shortlist') {
    return send(res, 200, sortSoonest(s.items.filter((i) => s.states[i.id] === 'saved' || s.states[i.id] === 'acting').map(withState)));
  }
  if (opp) {
    const item = s.items.find((i) => i.id === decodeURIComponent(opp[1]!));
    if (!item) return send(res, 404, { detail: 'Not found' });
    if (method === 'GET' && !opp[2]) {
      return send(res, 200, { ...withState(item), detail: { ...(item.detail as object), note: s.notes[item.id] ?? null, sources: [], documents: [], changes: [], fields: [] } });
    }
    if (method === 'PUT' && opp[2] === '/state') {
      const state = (body as { state?: string } | null)?.state;
      if (!state || !STATES.has(state)) return send(res, 422, { detail: 'Unknown state' });
      s.states[item.id] = state;
      return send(res, 200, { state });
    }
    if (method === 'PUT' && opp[2] === '/note') {
      s.notes[item.id] = String((body as { note?: unknown } | null)?.note ?? '');
      return send(res, 200, { note: s.notes[item.id] });
    }
  }
  if (method === 'GET' && path === '/profiles') return send(res, 200, s.profiles);
  if (method === 'POST' && path === '/profiles') {
    const p = { id: `p${s.profiles.length + 10}`, version: 1, active: true, ...(body as object) };
    s.profiles.push(p);
    return send(res, 201, p);
  }
  if (prof) {
    const i = s.profiles.findIndex((p) => p.id === prof[1]);
    if (i < 0) return send(res, 404, { detail: 'Not found' });
    if (method === 'PATCH') {
      const before = s.profiles[i]!;
      s.profiles[i] = { ...before, ...(body as object), version: Number(before.version) + 1 };
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
      s.digest = { ...s.digest, ...b, day: 'mon', channel: 'email' };
      return send(res, 200, s.digest);
    }
  }
  return send(res, 404, { detail: 'Not found' });
}

export function startStubApi(port: number): Promise<{ close: () => Promise<void> }> {
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
      if (!id) return send(res, 401, { detail: 'Sign in first.' });
      member(session(id), method, path, body, res);
    });
  });
  return new Promise((resolve, reject) => {
    server.on('error', reject);
    server.listen(port, '127.0.0.1', () => resolve({ close: () => new Promise((r) => server.close(() => r())) }));
  });
}
