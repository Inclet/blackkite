/** Admin API answers in the shapes the API sends (camelCase; contract 4.1). GET /me stays snake_case. */
export const ADMIN_ME = { id: 'u1', email: 'clet@example.rw', name: 'Clet', role: 'admin' };
export const MEMBER_ME = { id: 'u2', email: 'amina@example.rw', name: 'Amina', role: 'member' };

/** GET /api/admin/collector-types, the real API answer (tests/fixtures/collector-types.json, dumped from api CollectorTypeOut by alias). */
export { default as COLLECTOR_TYPES } from '../../../tests/fixtures/collector-types.json';

export function adminSource(over: Record<string, unknown> = {}) {
  return {
    id: 'src-1',
    name: 'Umucyo e-procurement',
    homeUrl: 'https://www.umucyo.gov.rw/',
    publisher: 'RPPA',
    streams: ['tender'],
    kind: 'original',
    collectorType: 'html_list',
    config: { list_url: 'https://www.umucyo.gov.rw/tenders', selectors: { item: 'tr', title: 'td a', link: 'td a' }, max_pages: 1 },
    schedule: null,
    effectiveSchedule: '0 */6 * * *',
    rateLimit: 5,
    accessNote: 'Tested from the host 24 Nov.',
    status: 'testing',
    addedBy: 'u1',
    createdAt: '2026-11-20T08:00:00Z',
    updatedAt: '2026-11-24T08:00:00Z',
    configChangedAt: '2026-11-22T08:00:00Z',
    health: 'ok',
    lastSuccessAt: '2026-11-24T04:00:00Z',
    lastRunAt: '2026-11-24T04:00:00Z',
    items30d: 9,
    promotionRuns: 1,
    promotionGate: { goodRuns: 1, needed: 2, since: '2026-11-22T08:00:00Z', met: false },
    statusHistory: [{ at: '2026-11-20T08:00:00Z', oldStatus: null, newStatus: 'testing', changedBy: 'u1', reason: 'created' }],
    ...over,
  };
}

export const RUN_ITEMS = [
  { id: 'r2', startedAt: '2026-11-24T04:00:00Z', finishedAt: '2026-11-24T04:01:00Z', status: 'succeeded', itemsFound: 9, itemsNew: 2, itemsFailed: 0, error: null },
  { id: 'r1', startedAt: '2026-11-23T22:00:00Z', finishedAt: '2026-11-23T22:00:30Z', status: 'failed', itemsFound: 0, itemsNew: 0, itemsFailed: 0, error: 'HTTP 503 from www.umucyo.gov.rw' },
];
export const RUNS = { total: 2, items: RUN_ITEMS };
export const FAILED_RUNS = { total: 1, items: RUN_ITEMS.filter((r) => r.status === 'failed') };

export const PREVIEW = {
  ok: true,
  error: null,
  items: [
    {
      url: 'https://www.umucyo.gov.rw/t/1',
      title: 'Supply of cold-chain transport',
      organisation: 'Rwanda Agriculture Board',
      listedPublished: '20 Nov 2026',
      listedDeadline: '8 Dec 2026',
      snippet: 'Transport of vaccines',
      detailUrl: null,
      extra: {},
    },
  ],
  totalParsed: 14,
  requestsMade: 1,
  elapsedSeconds: 1.24,
};

export const SUGGESTION = {
  id: 'sg-1',
  userId: 'u2',
  url: 'https://www.rdb.rw/calls',
  note: 'Covers: RDB calls\nWhy it is useful: funding calls',
  status: 'suggested',
  createdAt: '2026-11-23T08:00:00Z',
  reviewedAt: null,
  reviewedBy: null,
  sourceId: null,
};

export const REVIEW_ITEM = {
  id: 'op-1',
  stream: 'tender',
  title: 'Construction of a warehouse',
  organisation: 'MINAGRI',
  status: 'open',
  verification: 'unverified',
  trust: 'conflict',
  needsReview: true,
  reviewReasons: [{ code: 'deadline_conflict', detail: 'Job in Rwanda says 3 Dec; The New Times says 10 Dec.' }],
  deadline: '2026-12-03',
  memberVisible: true,
  sources: [
    { name: 'Job in Rwanda, tenders', status: 'active', kind: 'publisher', isOriginal: false, url: 'https://www.jobinrwanda.com/x' },
    { name: 'The New Times jobs', status: 'testing', kind: 'publisher', isOriginal: false, url: 'https://jobs.newtimes.co.rw/x' },
  ],
  createdAt: '2026-11-22T08:00:00Z',
  updatedAt: '2026-11-22T08:00:00Z',
};

export const USERS = [
  { id: 'u1', email: 'clet@example.rw', name: 'Clet', role: 'admin', status: 'active', createdAt: '2026-11-01T08:00:00Z', lastSignInAt: '2026-11-24T07:00:00Z' },
  { id: 'u2', email: 'amina@example.rw', name: null, role: 'member', status: 'active', createdAt: '2026-11-10T08:00:00Z', lastSignInAt: null },
];

export const INVITES = [
  { id: 'i1', email: 'eric@example.rw', invitedBy: 'u1', createdAt: '2026-11-20T08:00:00Z', expiresAt: '2026-11-27T08:00:00Z', acceptedAt: null, status: 'pending' },
];
