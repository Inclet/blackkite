/** Admin API answers in the shapes the API sends (snake_case for sources, users and invites). */
export const ADMIN_ME = { id: 'u1', email: 'clet@example.rw', name: 'Clet', role: 'admin' };
export const MEMBER_ME = { id: 'u2', email: 'amina@example.rw', name: 'Amina', role: 'member' };

export const COLLECTOR_TYPES = [
  {
    type: 'html_list',
    label: 'Web page list',
    fields: [
      { name: 'list_url', type: 'url', required: true, help: 'The page that lists the notices.' },
      { name: 'selectors.item', type: 'string', required: true, help: 'CSS for one notice.' },
      { name: 'selectors.title', type: 'string', required: true, help: null },
      { name: 'max_pages', type: 'integer', required: false, help: 'Pages to follow, 1 to 20.' },
    ],
  },
  {
    type: 'search_query',
    fields: [
      { name: 'queries', type: 'list', required: true, help: 'What to search for.' },
      { name: 'domains', type: 'list', required: false, help: null },
      { name: 'recency_days', type: 'integer', required: false, help: null },
    ],
  },
  { type: 'rss', fields: [{ name: 'feed_url', type: 'url', required: true, help: 'The feed address.' }] },
  { type: 'email_ingest', fields: [{ name: 'sender', type: 'string', required: true, help: null }, { name: 'strip_footer', type: 'boolean', required: false, help: 'Drop the footer.' }] },
];

export function adminSource(over: Record<string, unknown> = {}) {
  return {
    id: 'src-1',
    name: 'Umucyo e-procurement',
    home_url: 'https://www.umucyo.gov.rw/',
    publisher: 'RPPA',
    streams: ['tender'],
    kind: 'original',
    collector_type: 'html_list',
    config: { list_url: 'https://www.umucyo.gov.rw/tenders', selectors: { item: 'tr', title: 'td a', link: 'td a' }, max_pages: 1 },
    schedule: null,
    effective_schedule: '0 */6 * * *',
    rate_limit: 5,
    access_note: 'Tested from the host 24 Nov.',
    status: 'testing',
    added_by: 'u1',
    created_at: '2026-11-20T08:00:00Z',
    updated_at: '2026-11-24T08:00:00Z',
    config_changed_at: '2026-11-22T08:00:00Z',
    health: 'ok',
    last_success_at: '2026-11-24T04:00:00Z',
    last_run_at: '2026-11-24T04:00:00Z',
    items_30d: 9,
    promotion_runs: 1,
    ...over,
  };
}

export const RUNS = [
  { id: 'r2', started_at: '2026-11-24T04:00:00Z', finished_at: '2026-11-24T04:01:00Z', status: 'succeeded', items_found: 9, items_new: 2, items_failed: 0, error: null },
  { id: 'r1', started_at: '2026-11-23T22:00:00Z', finished_at: '2026-11-23T22:00:30Z', status: 'failed', items_found: 0, items_new: 0, items_failed: 0, error: 'HTTP 503 from www.umucyo.gov.rw' },
];

export const PREVIEW = {
  ok: true,
  error: null,
  items: [
    {
      url: 'https://www.umucyo.gov.rw/t/1',
      title: 'Supply of cold-chain transport',
      organisation: 'Rwanda Agriculture Board',
      listed_published: '20 Nov 2026',
      listed_deadline: '8 Dec 2026',
      snippet: 'Transport of vaccines',
      detail_url: null,
      extra: {},
    },
  ],
  total_parsed: 14,
  requests_made: 1,
  elapsed_seconds: 1.24,
};

export const SUGGESTION = {
  id: 'sg-1',
  user_id: 'u2',
  url: 'https://www.rdb.rw/calls',
  note: 'Covers: RDB calls\nWhy it is useful: funding calls',
  status: 'suggested',
  created_at: '2026-11-23T08:00:00Z',
  reviewed_at: null,
  reviewed_by: null,
  source_id: null,
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
  { id: 'u1', email: 'clet@example.rw', name: 'Clet', role: 'admin', status: 'active', created_at: '2026-11-01T08:00:00Z' },
  { id: 'u2', email: 'amina@example.rw', name: null, role: 'member', status: 'active', created_at: '2026-11-10T08:00:00Z' },
];

export const INVITES = [
  { id: 'i1', email: 'eric@example.rw', invited_by: 'u1', created_at: '2026-11-20T08:00:00Z', expires_at: '2026-11-27T08:00:00Z', accepted_at: null, status: 'pending' },
];
