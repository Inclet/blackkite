import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { mockApi, status } from '../../test/mockApi';
import { renderAt, setViewport } from '../feed/testUtils';
import { SIGN_IN } from '../SignIn';
import { COPY } from '../common/copy';
import { SOURCES_COPY, suggestionNote, validUrl } from './Sources';

const ME = { id: 'u', email: 'c@x.rw', name: 'Clet', role: 'member' };

/** As GET /api/sources sends it (api MemberSourceOut). */
const SOURCES = [
  {
    id: 's1',
    name: 'Umucyo e-procurement',
    homeUrl: 'https://www.umucyo.gov.rw/',
    publisher: 'Rwanda Public Procurement Authority',
    kind: 'original',
    streams: ['tender'],
    lastSuccessAt: '2026-11-24T04:00:00Z',
    items30d: 12,
    health: 'ok',
    muted: false,
  },
  {
    id: 's2',
    name: 'KT Press business',
    homeUrl: 'https://www.ktpress.rw/',
    publisher: null,
    kind: 'news',
    streams: ['funding', 'event'],
    lastSuccessAt: null,
    items30d: 1,
    health: 'failing',
    muted: true,
  },
];

beforeEach(() => setViewport('desktop'));
afterEach(() => vi.unstubAllGlobals());

function routes(extra: Record<string, unknown> = {}) {
  return mockApi({ 'GET /me': ME, 'GET /api/sources': SOURCES, 'GET /api/source-suggestions': [], ...extra });
}

test('lists active sources with publisher, kind, streams, last good run, items in 30 days and health in words', async () => {
  routes();
  renderAt('/sources');
  const list = within(await screen.findByRole('region', { name: SOURCES_COPY.listLabel }));
  expect(list.getByText('Umucyo e-procurement')).toBeInTheDocument();
  expect(list.getByText('Rwanda Public Procurement Authority · The issuer itself · Tenders')).toBeInTheDocument();
  expect(list.getByText('Last worked 24 Nov 2026, 06:00 · 12 items in the last 30 days')).toBeInTheDocument();
  expect(list.getByText('Health: Working')).toBeInTheDocument();
  expect(list.getByText('News · Funding, Events')).toBeInTheDocument();
  expect(list.getByText('Has not worked yet · 1 item in the last 30 days')).toBeInTheDocument();
  expect(list.getByText('Health: Failing')).toBeInTheDocument();
  expect(list.getByText('Its last checks failed.')).toBeInTheDocument();
  expect(list.getByRole('switch', { name: 'Mute Umucyo e-procurement' })).toHaveAttribute('aria-checked', 'false');
  expect(list.getByRole('switch', { name: 'Mute KT Press business' })).toHaveAttribute('aria-checked', 'true');
  // The sidebar marks Sources current.
  expect(within(screen.getByRole('navigation', { name: 'Main' })).getByRole('link', { name: 'Sources' })).toHaveAttribute('aria-current', 'page');
});

test('mute and unmute: POST and DELETE /api/sources/{id}/mute, announced', async () => {
  const api = routes({ 'POST /api/sources/s1/mute': undefined, 'DELETE /api/sources/s2/mute': undefined });
  renderAt('/sources');
  const sw = await screen.findByRole('switch', { name: 'Mute Umucyo e-procurement' });
  fireEvent.click(sw);
  expect(sw).toHaveAttribute('aria-checked', 'true');
  expect(await screen.findByText(SOURCES_COPY.muted('Umucyo e-procurement'))).toBeInTheDocument();
  fireEvent.click(screen.getByRole('switch', { name: 'Mute KT Press business' }));
  expect(await screen.findByText(SOURCES_COPY.unmuted('KT Press business'))).toBeInTheDocument();
  expect(api.calls.map((c) => c.key)).toEqual(expect.arrayContaining(['POST /api/sources/s1/mute', 'DELETE /api/sources/s2/mute']));
});

test('a mute that fails is undone and says so', async () => {
  routes({ 'POST /api/sources/s1/mute': status(503) });
  renderAt('/sources');
  const sw = await screen.findByRole('switch', { name: 'Mute Umucyo e-procurement' });
  fireEvent.click(sw);
  expect(await screen.findByText(COPY.actionFailed)).toBeInTheDocument();
  expect(sw).toHaveAttribute('aria-checked', 'false');
});

test('suggest a source: the address is checked, then sent with what it covers and why; it joins "Your suggestions"', async () => {
  const api = routes({
    'POST /api/source-suggestions': (body: { url: string; note: string }) => ({
      id: 'g1',
      url: body.url,
      note: body.note,
      status: 'suggested',
      createdAt: '2026-11-24T12:00:00Z',
      reviewedAt: null,
      sourceId: null,
    }),
  });
  renderAt('/sources');
  const form = within(await screen.findByRole('form', { name: SOURCES_COPY.suggestLabel }));
  fireEvent.click(form.getByRole('button', { name: SOURCES_COPY.send }));
  expect(form.getByLabelText(SOURCES_COPY.url)).toHaveAccessibleDescription(SOURCES_COPY.urlRequired);
  fireEvent.change(form.getByLabelText(SOURCES_COPY.url), { target: { value: 'rdb.rw' } });
  fireEvent.click(form.getByRole('button', { name: SOURCES_COPY.send }));
  expect(form.getByLabelText(SOURCES_COPY.url)).toHaveAccessibleDescription(SOURCES_COPY.urlInvalid);
  expect(api.calls.some((c) => c.key === 'POST /api/source-suggestions')).toBe(false);

  fireEvent.change(form.getByLabelText(SOURCES_COPY.url), { target: { value: ' https://rdb.rw/calls ' } });
  fireEvent.change(form.getByLabelText(SOURCES_COPY.covers), { target: { value: 'RDB calls for proposals' } });
  fireEvent.change(form.getByLabelText(SOURCES_COPY.why), { target: { value: 'Funding calls appear here first' } });
  fireEvent.click(form.getByRole('button', { name: SOURCES_COPY.send }));
  expect(await screen.findByText(SOURCES_COPY.sent)).toBeInTheDocument();
  expect(api.calls.find((c) => c.key === 'POST /api/source-suggestions')!.body).toEqual({
    url: 'https://rdb.rw/calls',
    note: 'Covers: RDB calls for proposals\nWhy it is useful: Funding calls appear here first',
  });
  const yours = within(screen.getByRole('region', { name: SOURCES_COPY.yours }));
  expect(yours.getByText('https://rdb.rw/calls')).toBeInTheDocument();
  expect(yours.getByText('Waiting for review')).toBeInTheDocument();
  expect(form.getByLabelText(SOURCES_COPY.url)).toHaveValue('');
});

test('a refused suggestion and an unreachable server say so', async () => {
  const api = routes({ 'POST /api/source-suggestions': status(422, { detail: 'blocked address' }) });
  renderAt('/sources');
  const form = within(await screen.findByRole('form', { name: SOURCES_COPY.suggestLabel }));
  fireEvent.change(form.getByLabelText(SOURCES_COPY.url), { target: { value: 'https://intranet.example.rw' } });
  fireEvent.click(form.getByRole('button', { name: SOURCES_COPY.send }));
  expect(await screen.findByText(SOURCES_COPY.refused)).toBeInTheDocument();
  api.on('POST /api/source-suggestions', status(500));
  fireEvent.click(form.getByRole('button', { name: SOURCES_COPY.send }));
  expect(await screen.findByText(/Your suggestion was not sent/)).toBeInTheDocument();
});

test('your earlier suggestions show their status in words', async () => {
  routes({
    'GET /api/source-suggestions': [
      { id: 'a', url: 'https://a.rw', note: null, status: 'accepted', createdAt: '2026-11-20T08:00:00Z', reviewedAt: null, sourceId: null },
      { id: 'b', url: 'https://b.rw', note: null, status: 'rejected', createdAt: '2026-11-19T08:00:00Z', reviewedAt: null, sourceId: null },
    ],
  });
  renderAt('/sources');
  const yours = within(await screen.findByRole('region', { name: SOURCES_COPY.yours }));
  expect(yours.getByText('Accepted')).toBeInTheDocument();
  expect(yours.getByText('Not taken up')).toBeInTheDocument();
  expect(yours.getByText('Sent 20 Nov 2026')).toBeInTheDocument();
});

test('no sources yet: a plain card, and the form is still there', async () => {
  routes({ 'GET /api/sources': [] });
  renderAt('/sources');
  expect(await screen.findByText(SOURCES_COPY.emptyTitle)).toBeInTheDocument();
  expect(screen.getByRole('form', { name: SOURCES_COPY.suggestLabel })).toBeInTheDocument();
});

test('no session: the sign-in screen', async () => {
  mockApi({ 'GET /api/sources': status(401), 'GET /api/source-suggestions': status(401) });
  renderAt('/sources');
  expect(await screen.findByRole('button', { name: SIGN_IN.button })).toBeInTheDocument();
});

test('phone: the same screen in the phone frame', async () => {
  setViewport('phone');
  routes();
  renderAt('/sources');
  await waitFor(() => expect(screen.getAllByRole('switch')).toHaveLength(2));
  expect(screen.getByRole('link', { name: 'More' })).toHaveAttribute('aria-current', 'page');
});

test('helpers', () => {
  expect(suggestionNote(' ', '')).toBeNull();
  expect(suggestionNote('x', '')).toBe('Covers: x');
  expect(validUrl('ftp://x.rw')).toBe(SOURCES_COPY.urlInvalid);
  expect(validUrl('https://localhost')).toBe(SOURCES_COPY.urlInvalid);
  expect(validUrl('https://x.rw')).toBeNull();
});
