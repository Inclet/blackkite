import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { mockApi, status } from '../../test/mockApi';
import { renderAt, setViewport } from '../feed/testUtils';
import { SIGN_IN } from '../SignIn';
import { ADMIN_LINKS, ADMIN_ONLY } from './AdminOnly';
import { ADMIN_SOURCES_COPY } from './AdminSources';
import { REVIEW_COPY } from './AdminReview';
import { SUGGESTIONS_COPY } from './AdminSuggestions';
import { USERS_COPY } from './AdminUsers';
import { EDITOR_COPY } from './SourceEditor';
import { ADMIN_ME, adminSource, COLLECTOR_TYPES, INVITES, MEMBER_ME, PREVIEW, REVIEW_ITEM, RUNS, SUGGESTION, USERS } from './testData';

beforeEach(() => setViewport('desktop'));
afterEach(() => vi.unstubAllGlobals());

const ADMIN_ROUTES = ['/admin', '/admin/sources', '/admin/sources/new', '/admin/sources/src-1', '/admin/suggestions', '/admin/review', '/admin/users'];

test.each(ADMIN_ROUTES)('%s for a member: "This page is for admins." and no admin API call or nav', async (url) => {
  const api = mockApi({ 'GET /me': MEMBER_ME });
  renderAt(url);
  expect(await screen.findByText(ADMIN_ONLY)).toBeInTheDocument();
  expect(api.calls.filter((c) => c.key.includes('/api/admin'))).toEqual([]);
  expect(within(screen.getByRole('navigation', { name: 'Main' })).queryByRole('link', { name: 'Admin' })).toBeNull();
});

test('an admin API that answers 403 shows the same refusal', async () => {
  mockApi({ 'GET /me': ADMIN_ME, 'GET /api/admin/sources': status(403, { detail: 'Admins only' }) });
  renderAt('/admin/sources');
  expect(await screen.findByText(ADMIN_ONLY)).toBeInTheDocument();
});

test('no session: sign in', async () => {
  mockApi({ 'GET /me': status(401) });
  renderAt('/admin/users');
  expect(await screen.findByRole('button', { name: SIGN_IN.button })).toBeInTheDocument();
});

test('/admin: links to the four admin screens, with Admin current in the sidebar', async () => {
  mockApi({ 'GET /me': ADMIN_ME });
  renderAt('/admin');
  const card = within(await screen.findByRole('region', { name: 'Admin screens' }));
  expect(card.getAllByRole('link').map((l) => [l.textContent, l.getAttribute('href')])).toEqual(ADMIN_LINKS.map((l) => [l.label, l.to]));
  expect(within(screen.getByRole('navigation', { name: 'Main' })).getByRole('link', { name: 'Admin' })).toHaveAttribute('aria-current', 'page');
});

test('/admin/sources: grouped by status with health in words, last run and the gate for testing sources', async () => {
  mockApi({
    'GET /me': ADMIN_ME,
    'GET /api/admin/sources': [
      adminSource(),
      adminSource({ id: 'src-2', name: 'RSE bonds', status: 'active', health: 'degraded', kind: 'original', streams: ['investment'], promotion_runs: 3 }),
      adminSource({ id: 'src-3', name: 'Old board', status: 'retired', health: 'unknown', last_run_at: null }),
    ],
  });
  renderAt('/admin/sources');
  const active = within(await screen.findByRole('region', { name: 'Active' }));
  expect(active.getByText('RSE bonds')).toBeInTheDocument();
  expect(active.getByText('Health: Some problems')).toBeInTheDocument();
  const testing = within(screen.getByRole('region', { name: 'Testing' }));
  expect(testing.getByText('Needs 2 good runs since the last config change: 1 so far.')).toBeInTheDocument();
  expect(testing.getByText('Last run 24 Nov 2026, 06:00 · 9 items in the last 30 days')).toBeInTheDocument();
  expect(testing.getByRole('link', { name: 'Edit Umucyo e-procurement' })).toHaveAttribute('href', '/admin/sources/src-1');
  expect(within(screen.getByRole('region', { name: 'Retired' })).getByText(/Never run/)).toBeInTheDocument();
  // Groups in order: active, testing, …, retired.
  expect(screen.getAllByRole('region').map((r) => r.getAttribute('aria-label'))).toEqual(['Active', 'Testing', 'Retired']);
  expect(screen.getByRole('button', { name: ADMIN_SOURCES_COPY.add })).toBeInTheDocument();
});

function editorRoutes(extra: Record<string, unknown> = {}) {
  return mockApi({
    'GET /me': ADMIN_ME,
    'GET /api/admin/collector-types': COLLECTOR_TYPES,
    'GET /api/admin/sources/src-1': adminSource(),
    'GET /api/admin/sources/src-1/runs': RUNS,
    ...extra,
  });
}

test('new source: the config form is rendered from collector-types; a test run previews and saves nothing; save creates it as testing', async () => {
  const api = editorRoutes({
    'POST /api/admin/sources/test-run': PREVIEW,
    'POST /api/admin/sources': (body: Record<string, unknown>) => adminSource({ ...body, id: 'src-9', status: 'testing', promotion_runs: 0 }),
    'GET /api/admin/sources/src-9': adminSource({ id: 'src-9', name: 'NCST calls', status: 'testing', promotion_runs: 0 }),
    'GET /api/admin/sources/src-9/runs': [],
  });
  const router = renderAt('/admin/sources/new');
  const form = within(await screen.findByRole('form', { name: EDITOR_COPY.newTitle }));
  fireEvent.click(form.getByRole('button', { name: 'RSS feed' }));
  expect(form.getByLabelText('Feed url')).toHaveAccessibleDescription('The feed address.');
  fireEvent.click(form.getByRole('button', { name: 'Web page list' }));
  expect(form.queryByLabelText('Feed url')).toBeNull();
  expect(form.getByLabelText('Selectors: item')).toBeInTheDocument();
  expect(form.getByLabelText('Max pages (optional)')).toBeInTheDocument();

  // A test run checks only the config.
  fireEvent.click(screen.getByRole('button', { name: EDITOR_COPY.testRun }));
  expect(await screen.findByText(EDITOR_COPY.checkFields)).toBeInTheDocument();
  expect(form.getByLabelText('List url')).toHaveAccessibleDescription(`The page that lists the notices. This is needed for this collector.`);
  fireEvent.change(form.getByLabelText('List url'), { target: { value: 'https://www.ncst.gov.rw/calls' } });
  fireEvent.change(form.getByLabelText('Selectors: item'), { target: { value: 'article' } });
  fireEvent.change(form.getByLabelText('Selectors: title'), { target: { value: 'h2 a' } });
  fireEvent.click(screen.getByRole('button', { name: EDITOR_COPY.testRun }));
  const preview = within(await screen.findByRole('region', { name: EDITOR_COPY.previewLabel }));
  expect(preview.getByText('Supply of cold-chain transport')).toBeInTheDocument();
  expect(preview.getByText('Published 20 Nov 2026 · Closes 8 Dec 2026')).toBeInTheDocument();
  expect(preview.getByText('Parsed 14 items with 1 request in 1.2 s. Showing the first 1.')).toBeInTheDocument();
  expect(preview.getByText(EDITOR_COPY.previewNothingSaved)).toBeInTheDocument();
  expect(api.calls.find((c) => c.key === 'POST /api/admin/sources/test-run')!.body).toEqual({
    collector_type: 'html_list',
    config: { list_url: 'https://www.ncst.gov.rw/calls', selectors: { item: 'article', title: 'h2 a' } },
    home_url: null,
    streams: ['tender'],
    rate_limit: null,
  });
  expect(api.calls.some((c) => c.key === 'POST /api/admin/sources')).toBe(false);

  // Save needs the record.
  fireEvent.click(form.getByRole('button', { name: EDITOR_COPY.create }));
  expect(await screen.findByText(EDITOR_COPY.checkFields)).toBeInTheDocument();
  fireEvent.change(form.getByLabelText(EDITOR_COPY.name), { target: { value: 'NCST calls' } });
  fireEvent.change(form.getByLabelText(EDITOR_COPY.homeUrl), { target: { value: 'https://www.ncst.gov.rw/' } });
  fireEvent.click(form.getByRole('button', { name: 'Funding' }));
  fireEvent.click(form.getByRole('button', { name: 'The issuer itself' }));
  fireEvent.click(form.getByRole('button', { name: EDITOR_COPY.create }));
  await waitFor(() => expect(router.state.location.pathname).toBe('/admin/sources/src-9'));
  expect(api.calls.find((c) => c.key === 'POST /api/admin/sources')!.body).toEqual({
    name: 'NCST calls',
    home_url: 'https://www.ncst.gov.rw/',
    publisher: null,
    streams: ['funding'],
    kind: 'original',
    collector_type: 'html_list',
    config: { list_url: 'https://www.ncst.gov.rw/calls', selectors: { item: 'article', title: 'h2 a' } },
    schedule: null,
    rate_limit: null,
    access_note: null,
  });
  expect(await screen.findByText(EDITOR_COPY.created)).toBeInTheDocument();
});

test('a failed test run shows its error; a refused one the API\'s reason', async () => {
  const api = editorRoutes({ 'POST /api/admin/sources/test-run': { ...PREVIEW, ok: false, error: 'HTTP 403 from www.umucyo.gov.rw', items: [], total_parsed: 0 } });
  renderAt('/admin/sources/src-1');
  fireEvent.click(await screen.findByRole('button', { name: EDITOR_COPY.testRun }));
  expect(await screen.findByText(EDITOR_COPY.previewFailed('HTTP 403 from www.umucyo.gov.rw'))).toBeInTheDocument();
  api.on('POST /api/admin/sources/test-run', status(422, { detail: [{ loc: ['body', 'config'], msg: 'selector does not parse' }] }));
  fireEvent.click(screen.getByRole('button', { name: EDITOR_COPY.testRun }));
  expect(await screen.findByText(EDITOR_COPY.previewRefused('config: selector does not parse'))).toBeInTheDocument();
});

test('existing source: record and config filled in; status with the promotion gate; a refused promotion explains the gate', async () => {
  const api = editorRoutes({ 'POST /api/admin/sources/src-1/status': status(409, { detail: 'needs 2 successful runs that found items since its config last changed; has 1' }) });
  renderAt('/admin/sources/src-1');
  const form = within(await screen.findByRole('form', { name: 'Umucyo e-procurement' }));
  expect(form.getByLabelText(EDITOR_COPY.name)).toHaveValue('Umucyo e-procurement');
  expect(form.getByLabelText('List url')).toHaveValue('https://www.umucyo.gov.rw/tenders');
  expect(form.getByLabelText(EDITOR_COPY.schedule)).toHaveAccessibleDescription('Leave empty for the default: 0 */6 * * *.');
  expect(form.getByRole('button', { name: 'Web page list' })).toHaveAttribute('aria-pressed', 'true');

  const card = within(screen.getByRole('region', { name: EDITOR_COPY.statusRegion }));
  expect(card.getByText(/Needs 2 good runs since the last config change: 1 so far\./)).toBeInTheDocument();
  expect(card.getAllByRole('button').map((b) => b.textContent)).toEqual(['Make active', 'Pause', 'Retire']);
  fireEvent.click(card.getByRole('button', { name: 'Make active' }));
  expect(await card.findByText('Not changed: it stays testing. Needs 2 good runs since the last config change: 1 so far.')).toBeInTheDocument();
  expect(api.calls.find((c) => c.key === 'POST /api/admin/sources/src-1/status')!.body).toEqual({ status: 'active' });
});

test('status change: pause, and the buttons follow the new status', async () => {
  editorRoutes({ 'POST /api/admin/sources/src-1/status': adminSource({ status: 'paused' }) });
  renderAt('/admin/sources/src-1');
  const card = within(await screen.findByRole('region', { name: EDITOR_COPY.statusRegion }));
  fireEvent.click(card.getByRole('button', { name: 'Pause' }));
  expect(await card.findByText(/^Paused\. It is not checked/)).toBeInTheDocument();
  expect(card.getAllByRole('button').map((b) => b.textContent)).toEqual(['Make active again', 'Back to testing', 'Retire']);
});

test('saving an edit PATCHes the source; an active source warns that config changes send it back to testing', async () => {
  const api = editorRoutes({
    'GET /api/admin/sources/src-1': adminSource({ status: 'active', promotion_runs: 2 }),
    'PATCH /api/admin/sources/src-1': (body: Record<string, unknown>) => adminSource({ ...body, status: 'testing' }),
  });
  renderAt('/admin/sources/src-1');
  expect(await screen.findByText(EDITOR_COPY.activeWarning)).toBeInTheDocument();
  const form = within(screen.getByRole('form', { name: 'Umucyo e-procurement' }));
  fireEvent.change(form.getByLabelText('Max pages (optional)'), { target: { value: '2' } });
  fireEvent.click(form.getByRole('button', { name: EDITOR_COPY.save }));
  expect(await screen.findByText(EDITOR_COPY.savedBackToTesting)).toBeInTheDocument();
  const body = api.calls.find((c) => c.key === 'PATCH /api/admin/sources/src-1')!.body as { config: unknown };
  expect(body.config).toEqual({ list_url: 'https://www.umucyo.gov.rw/tenders', selectors: { item: 'tr', title: 'td a', link: 'td a' }, max_pages: 2 });
});

test('a name already in use is said plainly', async () => {
  editorRoutes({ 'PATCH /api/admin/sources/src-1': status(409, { detail: 'A source with that name already exists' }) });
  renderAt('/admin/sources/src-1');
  fireEvent.click(await screen.findByRole('button', { name: EDITOR_COPY.save }));
  expect(await screen.findByText(EDITOR_COPY.nameTaken)).toBeInTheDocument();
});

test('run history and error log', async () => {
  editorRoutes();
  renderAt('/admin/sources/src-1');
  const runs = within(await screen.findByRole('region', { name: EDITOR_COPY.runs }));
  expect(runs.getByText('24 Nov 2026, 06:00')).toBeInTheDocument();
  expect(runs.getByText('9 found · 2 new')).toBeInTheDocument();
  expect(runs.getByText('Worked')).toBeInTheDocument();
  expect(runs.getByText('Failed')).toBeInTheDocument();
  const log = within(screen.getByRole('region', { name: EDITOR_COPY.errors }));
  expect(log.getByText('HTTP 503 from www.umucyo.gov.rw')).toBeInTheDocument();
});

test('collector types that fail to load: the config is edited as JSON', async () => {
  editorRoutes({ 'GET /api/admin/collector-types': status(500) });
  renderAt('/admin/sources/src-1');
  expect(await screen.findByText(EDITOR_COPY.typesFailed)).toBeInTheDocument();
  expect(screen.getByLabelText(EDITOR_COPY.wholeConfig)).toHaveValue(JSON.stringify(adminSource().config));
});

test('an unknown source says so', async () => {
  editorRoutes({ 'GET /api/admin/sources/nope': status(404), 'GET /api/admin/sources/nope/runs': status(404) });
  renderAt('/admin/sources/nope');
  expect(await screen.findByText(EDITOR_COPY.notFound)).toBeInTheDocument();
});

test('suggestions: accept, then "Create source from this" opens the editor prefilled and links the suggestion', async () => {
  let current: Record<string, unknown> = SUGGESTION;
  const api = mockApi({
    'GET /me': ADMIN_ME,
    'GET /api/admin/source-suggestions': (_b: unknown, url: string) => (url.includes(`status=${current.status}`) ? [current] : []),
    'POST /api/admin/source-suggestions/sg-1/accept': () => (current = { ...SUGGESTION, status: 'accepted', reviewed_by: 'u1' }),
    'GET /api/admin/collector-types': COLLECTOR_TYPES,
    'POST /api/admin/sources': (body: Record<string, unknown>) => adminSource({ ...body, id: 'src-7' }),
    'GET /api/admin/sources/src-7': adminSource({ id: 'src-7' }),
    'GET /api/admin/sources/src-7/runs': [],
  });
  const router = renderAt('/admin/suggestions');
  const waiting = within(await screen.findByRole('region', { name: SUGGESTIONS_COPY.waiting }));
  expect(waiting.getByText('https://www.rdb.rw/calls')).toBeInTheDocument();
  expect(waiting.getByText(/Why it is useful: funding calls/)).toBeInTheDocument();
  fireEvent.click(waiting.getByRole('button', { name: 'Accept https://www.rdb.rw/calls' }));
  expect(await screen.findByText(SUGGESTIONS_COPY.didAccept('https://www.rdb.rw/calls'))).toBeInTheDocument();
  expect(screen.getByText(SUGGESTIONS_COPY.none)).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: `${SUGGESTIONS_COPY.create}: https://www.rdb.rw/calls` }));
  await waitFor(() => expect(router.state.location.search).toBe('?suggestion=sg-1'));
  const from = within(await screen.findByRole('region', { name: EDITOR_COPY.fromSuggestion }));
  expect(from.getByText('https://www.rdb.rw/calls')).toBeInTheDocument();
  const form = within(screen.getByRole('form', { name: EDITOR_COPY.newTitle }));
  expect(form.getByLabelText(EDITOR_COPY.homeUrl)).toHaveValue('https://www.rdb.rw/calls');

  fireEvent.change(form.getByLabelText(EDITOR_COPY.name), { target: { value: 'RDB calls' } });
  fireEvent.click(form.getByRole('button', { name: 'Funding' }));
  fireEvent.click(form.getByRole('button', { name: 'The issuer itself' }));
  fireEvent.click(form.getByRole('button', { name: 'RSS feed' }));
  fireEvent.change(form.getByLabelText('Feed url'), { target: { value: 'https://www.rdb.rw/feed' } });
  fireEvent.click(form.getByRole('button', { name: EDITOR_COPY.create }));
  await waitFor(() => expect(router.state.location.pathname).toBe('/admin/sources/src-7'));
  expect(api.calls.find((c) => c.key === 'POST /api/admin/sources')!.body).toMatchObject({ suggestion_id: 'sg-1', home_url: 'https://www.rdb.rw/calls', collector_type: 'rss' });
});

test('suggestions: reject; one already reviewed says so', async () => {
  const api = mockApi({
    'GET /me': ADMIN_ME,
    'GET /api/admin/source-suggestions': (_b: unknown, url: string) => (url.includes('status=accepted') ? [] : [SUGGESTION, { ...SUGGESTION, id: 'sg-2', url: 'https://b.rw' }]),
    'POST /api/admin/source-suggestions/sg-1/reject': { ...SUGGESTION, status: 'rejected' },
    'POST /api/admin/source-suggestions/sg-2/reject': status(409, { detail: 'suggestion already accepted' }),
  });
  renderAt('/admin/suggestions');
  fireEvent.click(await screen.findByRole('button', { name: 'Reject https://www.rdb.rw/calls' }));
  expect(await screen.findByText(SUGGESTIONS_COPY.didReject('https://www.rdb.rw/calls'))).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Reject https://b.rw' }));
  expect(await screen.findByText(SUGGESTIONS_COPY.already)).toBeInTheDocument();
  expect(api.calls.filter((c) => c.key === 'GET /api/admin/source-suggestions').length).toBeGreaterThanOrEqual(3);
});

test('review: items with their reasons and sources; "Mark reviewed" clears one', async () => {
  const api = mockApi({
    'GET /me': ADMIN_ME,
    'GET /api/admin/catalogue': { total: 1, items: [REVIEW_ITEM] },
    'POST /api/admin/catalogue/op-1/review': { ...REVIEW_ITEM, needsReview: false, reviewReasons: [] },
  });
  renderAt('/admin/review');
  const card = within(await screen.findByRole('region', { name: 'Construction of a warehouse' }));
  expect(card.getByText('Job in Rwanda says 3 Dec; The New Times says 10 Dec.')).toBeInTheDocument();
  expect(card.getByText('Sources disagree on the date')).toBeInTheDocument();
  expect(card.getByText('The New Times jobs (Testing)')).toBeInTheDocument();
  expect(card.getByText('Closes 3 Dec')).toBeInTheDocument();
  expect(card.getByText(REVIEW_COPY.visible)).toBeInTheDocument();
  fireEvent.click(card.getByRole('button', { name: `${REVIEW_COPY.mark}: Construction of a warehouse` }));
  expect(await screen.findByText(REVIEW_COPY.marked('Construction of a warehouse'))).toBeInTheDocument();
  expect(screen.getByText(REVIEW_COPY.none)).toBeInTheDocument();
  expect(api.fetch.mock.calls.find(([u]) => String(u).startsWith('/api/admin/catalogue'))![0]).toBe('/api/admin/catalogue?needsReview=true');
});

test('users: role and status in words; invite by email (409 said plainly); deactivate with a confirm step; never yourself', async () => {
  const api = mockApi({
    'GET /me': ADMIN_ME,
    'GET /api/admin/users': USERS,
    'GET /api/admin/invites': INVITES,
    'POST /api/admin/invites': (body: { email: string }) =>
      body.email === 'clet@example.rw' ? status(409, { detail: 'That address already has an account' }) : { ...INVITES[0], id: 'i2', email: body.email },
    'POST /api/admin/users/u2/deactivate': { ...USERS[1], status: 'deactivated' },
    'DELETE /api/admin/invites/i1': undefined,
  });
  renderAt('/admin/users');
  const accounts = within(await screen.findByRole('region', { name: USERS_COPY.users }));
  expect(accounts.getByText('You')).toBeInTheDocument();
  expect(accounts.getAllByText('Active')).toHaveLength(2);
  expect(accounts.getByText('Admin')).toBeInTheDocument();
  expect(accounts.getByText('Member')).toBeInTheDocument();
  expect(accounts.queryByRole('button', { name: 'Deactivate clet@example.rw' })).toBeNull();

  const form = within(screen.getByRole('form', { name: USERS_COPY.invite }));
  fireEvent.change(form.getByLabelText(USERS_COPY.email), { target: { value: 'nope' } });
  fireEvent.click(form.getByRole('button', { name: USERS_COPY.send }));
  expect(form.getByLabelText(USERS_COPY.email)).toHaveAccessibleDescription(USERS_COPY.emailInvalid);
  fireEvent.change(form.getByLabelText(USERS_COPY.email), { target: { value: 'clet@example.rw' } });
  fireEvent.click(form.getByRole('button', { name: USERS_COPY.send }));
  expect(await form.findByText(USERS_COPY.already)).toBeInTheDocument();
  fireEvent.change(form.getByLabelText(USERS_COPY.email), { target: { value: 'grace@example.rw' } });
  fireEvent.click(form.getByRole('button', { name: USERS_COPY.send }));
  expect(await form.findByText(USERS_COPY.sent('grace@example.rw'))).toBeInTheDocument();
  expect(within(screen.getByRole('region', { name: USERS_COPY.invites })).getByText('grace@example.rw')).toBeInTheDocument();

  fireEvent.click(accounts.getByRole('button', { name: 'Deactivate amina@example.rw' }));
  expect(accounts.getByText(USERS_COPY.confirm('amina@example.rw'))).toBeInTheDocument();
  fireEvent.click(accounts.getByRole('button', { name: USERS_COPY.keep }));
  expect(api.calls.some((c) => c.key === 'POST /api/admin/users/u2/deactivate')).toBe(false);
  fireEvent.click(accounts.getByRole('button', { name: 'Deactivate amina@example.rw' }));
  fireEvent.click(accounts.getByRole('button', { name: USERS_COPY.confirmButton }));
  expect(await screen.findByText(USERS_COPY.didDeactivate('amina@example.rw'))).toBeInTheDocument();
  expect(accounts.getByText('Deactivated')).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Withdraw the invite to eric@example.rw' }));
  expect(await screen.findByText(USERS_COPY.withdrawn('eric@example.rw'))).toBeInTheDocument();
});

test('phone: admin screens sit under More', async () => {
  setViewport('phone');
  mockApi({ 'GET /me': ADMIN_ME });
  renderAt('/admin');
  await screen.findByRole('region', { name: 'Admin screens' });
  expect(screen.getByRole('link', { name: 'More' })).toHaveAttribute('aria-current', 'page');
});
