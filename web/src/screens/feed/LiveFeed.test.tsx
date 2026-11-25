import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { referenceItems } from '../../fixtures/reference';
import type { FeedContent } from '../../fixtures/types';
import { setNowForTests } from '../../lib/now';
import { mockApi, status } from '../../test/mockApi';
import { COPY } from '../common/copy';
import { SIGN_IN } from '../SignIn';
import { LIVE_COPY } from './parts';
import { renderAt, setViewport } from './testUtils';

beforeEach(() => {
  setNowForTests('2026-11-24T14:00:00+02:00');
  setViewport('desktop');
});
afterEach(() => {
  setNowForTests(null);
  vi.unstubAllGlobals();
});

const PROFILE = { id: 'p1', name: 'Ironji-Trade', type: 'business', data: {}, version: 1, active: true };

/** The reference items in a scrambled order: the screen ranks them closing soonest first. */
function feed(items = referenceItems().reverse()): FeedContent {
  return { user: { name: 'Clet' }, sources: { checked: 3, when: 'this morning' }, digest: { channel: 'email' }, items };
}

function liveApi(overrides: Record<string, unknown> = {}) {
  return mockApi({
    'GET /api/feed': feed(),
    'GET /api/shortlist': [],
    'GET /api/profiles': [PROFILE],
    'GET /me': { id: 'u', email: 'c@x.rw', name: 'Clet', role: 'admin' },
    'PUT /api/opportunities/wfp-logistics/state': {},
    'PUT /api/opportunities/abh-summit/state': {},
    ...overrides,
  });
}

const list = () => within(screen.getByRole('region', { name: 'Opportunities' }));
const rowTitles = () => list().getAllByRole('link').map((r) => r.querySelector('span span')?.textContent ?? r.textContent);
const saveButton = () => within(screen.getByRole('article')).getByRole('button', { name: 'Save to shortlist' });
const press = (key: string) => act(() => void fireEvent.keyDown(window, { key }));

/** The detail pane is on screen and its effects (the key listener among them) have run. */
async function ready() {
  const pane = await screen.findByRole('article');
  await act(async () => {});
  return pane;
}

test('loads from the API: the circling kite first, then the ranked list', async () => {
  const api = liveApi();
  renderAt('/');
  expect(screen.getByTestId('kite-orbit')).toBeInTheDocument();
  expect(screen.getByText(COPY.loadingTitle)).toBeInTheDocument();
  expect(await screen.findByRole('heading', { level: 1, name: 'Good afternoon, Clet' })).toBeInTheDocument();
  expect(screen.getByText('3 sources checked this morning')).toBeInTheDocument();
  const rows = list().getAllByRole('link');
  expect(rows).toHaveLength(6);
  // Closing soonest first, whatever order the API sent.
  expect(rows[0]).toHaveTextContent('Logistics, transport and warehousing support');
  expect(rows[5]).toHaveTextContent('Five-year treasury bond');
  expect(api.calls.map((c) => c.key)).toEqual(expect.arrayContaining(['GET /api/feed', 'GET /api/shortlist', 'GET /api/profiles']));
  expect(screen.queryByText(COPY.refreshingTitle)).toBeNull();
});

test('with ?fixture= nothing is fetched', () => {
  const api = liveApi();
  renderAt('/?fixture=reference');
  expect(screen.getByRole('heading', { level: 1, name: 'Good afternoon, Clet' })).toBeInTheDocument();
  expect(api.fetch).not.toHaveBeenCalled();
});

test('401: the sign-in screen', async () => {
  liveApi({ 'GET /api/feed': status(401, { detail: 'Sign in' }) });
  renderAt('/');
  expect(await screen.findByRole('heading', { level: 1, name: SIGN_IN.heading })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: SIGN_IN.button })).toBeInTheDocument();
});

test('unreachable: plain wording and Try again, which loads the feed', async () => {
  const api = liveApi({ 'GET /api/feed': status(502) });
  renderAt('/');
  expect(await screen.findByText(COPY.unreachableTitle)).toBeInTheDocument();
  expect(screen.queryByRole('progressbar')).toBeNull();
  api.on('GET /api/feed', feed());
  fireEvent.click(screen.getByRole('button', { name: COPY.tryAgain }));
  expect(await screen.findByRole('heading', { level: 1, name: 'Good afternoon, Clet' })).toBeInTheDocument();
});

test('coming back: the previous list stays on screen under the checking card', async () => {
  liveApi();
  const router = renderAt('/');
  await screen.findByRole('heading', { level: 1, name: 'Good afternoon, Clet' });
  let release!: () => void;
  const api2 = { gate: new Promise<void>((r) => (release = r)) };
  // The next load waits, so the cached list shows while it is checking.
  const { on } = liveApiKeepCache();
  on('GET /api/feed', async () => {
    await api2.gate;
    return feed();
  });
  await act(() => router.navigate('/shortlist'));
  await act(() => router.navigate('/'));
  expect(screen.getByText(COPY.refreshingTitle)).toBeInTheDocument();
  expect(list().getAllByRole('link')).toHaveLength(6);
  await act(async () => release());
  await waitFor(() => expect(screen.queryByText(COPY.refreshingTitle)).toBeNull());
});

/** Re-stub routes without clearing the cache. */
function liveApiKeepCache() {
  const table = new Map<string, unknown>([
    ['GET /api/shortlist', []],
    ['GET /api/profiles', [PROFILE]],
    ['GET /me', { id: 'u', email: 'c@x.rw', name: 'Clet', role: 'admin' }],
  ]);
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const h = table.get(`${init.method ?? 'GET'} ${url.split('?')[0]}`);
      const out = typeof h === 'function' ? await (h as () => unknown)() : h;
      return out === undefined ? status(404) : new Response(JSON.stringify(out), { status: 200 });
    }),
  );
  return { on: (k: string, h: unknown) => void table.set(k, h) };
}

test('saved items from /shortlist start pressed', async () => {
  liveApi({ 'GET /api/shortlist': [{ ...referenceItems()[0]!, state: 'saved' }] });
  renderAt('/');
  await waitFor(() => expect(saveButton()).toHaveAttribute('aria-pressed', 'true'));
});

test('save: pressed at once, sent with PUT; S unsaves', async () => {
  const api = liveApi();
  renderAt('/');
  await ready();
  fireEvent.click(saveButton());
  expect(saveButton()).toHaveAttribute('aria-pressed', 'true');
  await waitFor(() => expect(api.calls).toContainEqual({ key: 'PUT /api/opportunities/wfp-logistics/state', body: { state: 'saved' } }));
  press('s');
  expect(saveButton()).toHaveAttribute('aria-pressed', 'false');
  await waitFor(() => expect(api.calls).toContainEqual({ key: 'PUT /api/opportunities/wfp-logistics/state', body: { state: 'unseen' } }));
});

test('save that does not reach the server is undone, and says so', async () => {
  liveApi({ 'PUT /api/opportunities/wfp-logistics/state': status(503) });
  renderAt('/');
  await ready();
  fireEvent.click(saveButton());
  expect(saveButton()).toHaveAttribute('aria-pressed', 'true');
  await waitFor(() => expect(saveButton()).toHaveAttribute('aria-pressed', 'false'));
  expect(screen.getByRole('region', { name: 'Change not saved' })).toHaveTextContent(COPY.actionFailed);
  expect(screen.getAllByRole('status').some((s) => s.textContent === COPY.actionFailed)).toBe(true);
});

test('X dismisses with PUT; a failed dismissal brings the row back, and J reaches it again', async () => {
  const api = liveApi({ 'PUT /api/opportunities/wfp-logistics/state': status(500) });
  renderAt('/');
  await ready();
  press('x');
  expect(list().getAllByRole('link')).toHaveLength(5);
  await waitFor(() => expect(api.calls).toContainEqual({ key: 'PUT /api/opportunities/wfp-logistics/state', body: { state: 'dismissed' } }));
  await waitFor(() => expect(list().getAllByRole('link')).toHaveLength(6));
  // Selection moved to the next row; K goes back up to the restored one.
  press('k');
  await waitFor(() => expect(within(screen.getByRole('article')).getByRole('heading', { level: 2 })).toHaveTextContent('Logistics'));
});

test('a dismissal that is saved stays gone', async () => {
  liveApi();
  renderAt('/');
  await ready();
  press('x');
  await waitFor(() => expect(list().getAllByRole('link')).toHaveLength(5));
  expect(rowTitles()[0]).not.toContain('Logistics');
});

test('no profiles yet: the first-visit card, and the list unranked', async () => {
  liveApi({ 'GET /api/profiles': [] });
  const router = renderAt('/');
  expect(await screen.findByText('Tell Blackkite what you do')).toBeInTheDocument();
  expect(list().queryByText(/Strong fit/)).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Set up a profile' }));
  expect(router.state.location.pathname).toBe('/profiles');
});

test('an empty feed: nothing new, with live counts', async () => {
  liveApi({ 'GET /api/feed': feed([]), 'GET /api/shortlist': [{ ...referenceItems()[0]!, state: 'saved' }] });
  renderAt('/');
  expect(await screen.findByText('Nothing new since yesterday')).toBeInTheDocument();
  expect(screen.getByText('All 3 sources were checked this morning. Your shortlist has 1 item closing this month.')).toBeInTheDocument();
  expect(screen.queryByRole('region', { name: 'Opportunities' })).toBeNull();
});

test('acting and done chips, and the note, are saved with PUT', async () => {
  const api = liveApi({
    'GET /api/opportunities/wfp-logistics': { ...referenceItems()[0]!, detail: { ...referenceItems()[0]!.detail, note: 'Ask Eric' } },
    'PUT /api/opportunities/wfp-logistics/note': {},
  });
  renderAt('/');
  const pane = await ready();
  const note = within(pane).getByLabelText(LIVE_COPY.note);
  await waitFor(() => expect(note).toHaveValue('Ask Eric'));

  const acting = within(pane).getByRole('button', { name: LIVE_COPY.acting });
  fireEvent.click(acting);
  expect(acting).toHaveAttribute('aria-pressed', 'true');
  expect(saveButton()).toHaveAttribute('aria-pressed', 'true');
  await waitFor(() => expect(api.calls).toContainEqual({ key: 'PUT /api/opportunities/wfp-logistics/state', body: { state: 'acting' } }));
  fireEvent.click(within(pane).getByRole('button', { name: LIVE_COPY.done }));
  expect(acting).toHaveAttribute('aria-pressed', 'false');
  await waitFor(() => expect(api.calls).toContainEqual({ key: 'PUT /api/opportunities/wfp-logistics/state', body: { state: 'done' } }));

  fireEvent.change(note, { target: { value: 'Ask Eric about the partner trucks' } });
  // Typing in the note is not a feed key.
  fireEvent.keyDown(note, { key: 'x' });
  fireEvent.click(within(pane).getByRole('button', { name: LIVE_COPY.saveNote }));
  expect(await within(pane).findByText(LIVE_COPY.noteSaved)).toBeInTheDocument();
  expect(api.calls).toContainEqual({ key: 'PUT /api/opportunities/wfp-logistics/note', body: { note: 'Ask Eric about the partner trucks' } });
  expect(list().getAllByRole('link')).toHaveLength(6);
});

test('a note that does not reach the server keeps the text and shows the field error', async () => {
  liveApi({ 'PUT /api/opportunities/wfp-logistics/note': status(500) });
  renderAt('/');
  const pane = await ready();
  const note = within(pane).getByLabelText(LIVE_COPY.note);
  fireEvent.change(note, { target: { value: 'Call Tuesday' } });
  fireEvent.click(within(pane).getByRole('button', { name: LIVE_COPY.saveNote }));
  await waitFor(() => expect(note).toHaveAccessibleDescription(LIVE_COPY.noteFailed));
  expect(note).toHaveValue('Call Tuesday');
});

test('phone: the opportunity page saves through the API too', async () => {
  setViewport('phone');
  const api = liveApi();
  renderAt('/o/wfp-logistics');
  const save = await screen.findByRole('button', { name: 'Save to shortlist' });
  fireEvent.click(save);
  expect(save).toHaveAttribute('aria-pressed', 'true');
  await waitFor(() => expect(api.calls).toContainEqual({ key: 'PUT /api/opportunities/wfp-logistics/state', body: { state: 'saved' } }));
  expect(screen.getByLabelText(LIVE_COPY.note)).toBeInTheDocument();
});

test('phone: the account button opens the account screen', async () => {
  setViewport('phone');
  liveApi();
  const router = renderAt('/');
  await screen.findByRole('heading', { level: 1, name: 'Good afternoon, Clet' });
  fireEvent.click(screen.getByRole('button', { name: 'Your account' }));
  expect(router.state.location.pathname).toBe('/account');
});
