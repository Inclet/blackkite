import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { setNowForTests } from '../../lib/now';
import { mockApi, status } from '../../test/mockApi';
import { COPY } from '../common/copy';
import { renderAt, setViewport } from '../feed/testUtils';
import { SIGN_IN } from '../SignIn';
import { AWARDS_COPY } from './BenchmarkAwards';
import { BENCHMARKS_COPY } from './Benchmarks';

const ME = { id: 'u', email: 'c@x.rw', name: 'Clet', role: 'member' };

/** As GET /api/benchmarks sends it (contract section 6). */
const CATEGORIES = [
  { category: 'road-works', label: 'Road works', awards: 14, median: 6100000, p25: 4200000, p75: 9800000, min: 900000, max: 25000000, currency: 'RWF', medianBidders: 5 },
  { category: 'freight', label: 'Freight and transport', awards: 2, median: null, p25: null, p75: null, min: null, max: null, currency: 'RWF', medianBidders: null },
  { category: 'freight', label: 'Freight and transport', awards: 4, median: 61000, p25: '40000.00', p75: '90000.00', min: 30000, max: 120000, currency: 'USD', medianBidders: 3 },
];

const AWARD = {
  id: 'a1',
  tenderRef: 'RTDA/2026/014',
  entity: 'Rwanda Transport Development Agency',
  title: 'Maintenance of the Kigali–Musanze road',
  winner: 'Kigali Roads Ltd',
  winningPrice: '6120000.00',
  bidders: [
    { name: 'Kigali Roads Ltd', price: 6120000 },
    { name: 'Hills Construction', price: 7400000 },
    { name: 'Lake Works', price: null },
  ],
  awardedOn: '2026-10-02',
  url: 'https://www.umucyo.gov.rw/award/014',
};

beforeEach(() => {
  setNowForTests('2026-11-24T14:00:00+02:00');
  setViewport('desktop');
});
afterEach(() => {
  setNowForTests(null);
  vi.unstubAllGlobals();
});

test('each category in plain words, one currency per line, the currency named only when a category has two', async () => {
  const api = mockApi({ 'GET /me': ME, 'GET /api/benchmarks': { categories: CATEGORIES } });
  renderAt('/benchmarks');
  const list = within(await screen.findByRole('region', { name: BENCHMARKS_COPY.listLabel }));
  expect(list.getByText('Road works')).toBeInTheDocument();
  expect(list.getByText('Most awards were between FRW 4.2M and FRW 9.8M; the middle one was FRW 6.1M (14 awards). Usually 5 bidders.')).toBeInTheDocument();
  expect(list.getByText('Freight and transport (FRW)')).toBeInTheDocument();
  expect(list.getByText('Only 2 awards so far — not enough to show a range.')).toBeInTheDocument();
  expect(list.getByText('Freight and transport (USD)')).toBeInTheDocument();
  expect(list.getByText('Most awards were between USD 40,000 and USD 90,000; the middle one was USD 61,000 (4 awards). Usually 3 bidders.')).toBeInTheDocument();
  expect(list.getByRole('link', { name: BENCHMARKS_COPY.openLabel('Road works') })).toHaveAttribute('href', '/benchmarks/road-works');
  // The default window: the last 12 months, Kigali.
  expect(api.fetch.mock.calls.map((c) => c[0])).toContain('/api/benchmarks?from=2025-11-24&to=2026-11-24');
  // Numbers here are prices, never a score.
  expect(screen.queryByText(/score/i)).toBeNull();
});

test('period chips and the buying-organisation search change the query and stay in the address', async () => {
  const api = mockApi({ 'GET /me': ME, 'GET /api/benchmarks': { categories: CATEGORIES } });
  const router = renderAt('/benchmarks');
  await screen.findByRole('region', { name: BENCHMARKS_COPY.listLabel });
  const period = screen.getByRole('group', { name: BENCHMARKS_COPY.period });
  expect(within(period).getByRole('button', { name: '12 months' })).toHaveAttribute('aria-pressed', 'true');
  fireEvent.click(within(period).getByRole('button', { name: '2 years' }));
  await waitFor(() => expect(api.fetch.mock.calls.map((c) => c[0])).toContain('/api/benchmarks?from=2024-11-24&to=2026-11-24'));
  fireEvent.click(within(period).getByRole('button', { name: 'All' }));
  await waitFor(() => expect(api.fetch.mock.calls.map((c) => c[0])).toContain('/api/benchmarks'));
  expect(router.state.location.search).toBe('?period=all');

  const entity = screen.getByLabelText(BENCHMARKS_COPY.entity);
  expect(entity).toHaveAccessibleDescription(BENCHMARKS_COPY.entityHint);
  fireEvent.change(entity, { target: { value: 'RTDA' } });
  fireEvent.click(screen.getByRole('button', { name: BENCHMARKS_COPY.search }));
  await waitFor(() => expect(api.fetch.mock.calls.map((c) => c[0])).toContain('/api/benchmarks?entity=RTDA'));
  expect(router.state.location.search).toBe('?period=all&entity=RTDA');
  fireEvent.click(screen.getByRole('button', { name: BENCHMARKS_COPY.clear }));
  await waitFor(() => expect(router.state.location.search).toBe('?period=all'));
  expect(entity).toHaveValue('');
});

test('nothing found: plain wording for the filter in use', async () => {
  mockApi({ 'GET /me': ME, 'GET /api/benchmarks': { categories: [] } });
  renderAt('/benchmarks?period=all&entity=RTDA');
  expect(await screen.findByText(BENCHMARKS_COPY.emptyFiltered('RTDA'))).toBeInTheDocument();
  mockApi({ 'GET /me': ME, 'GET /api/benchmarks': { categories: [] } });
  renderAt('/benchmarks?period=all');
  expect(await screen.findAllByText(BENCHMARKS_COPY.emptyBody)).not.toHaveLength(0);
});

test('unreachable shows the source-down card; 401 signs in', async () => {
  mockApi({ 'GET /me': ME, 'GET /api/benchmarks': status(503) });
  renderAt('/benchmarks');
  expect(await screen.findByText(COPY.unreachableTitle)).toBeInTheDocument();
  mockApi({ 'GET /api/benchmarks': status(401) });
  renderAt('/benchmarks');
  expect(await screen.findAllByRole('heading', { name: SIGN_IN.title })).not.toHaveLength(0);
});

test('a category: its awards with winner, price, date, ref; bidders behind a real disclosure; the notice opens in a new tab', async () => {
  mockApi({ 'GET /me': ME, 'GET /api/benchmarks': { categories: CATEGORIES }, 'GET /api/benchmarks/road-works': { awards: [AWARD], total: 1 } });
  renderAt('/benchmarks/road-works');
  expect(await screen.findByRole('heading', { level: 1, name: 'Road works' })).toBeInTheDocument();
  const list = within(await screen.findByRole('region', { name: AWARDS_COPY.listLabel }));
  expect(list.getByText('Awards 1–1 of 1')).toBeInTheDocument();
  expect(list.getByText(AWARD.title)).toBeInTheDocument();
  expect(list.getByText('Rwanda Transport Development Agency · Awarded 2 Oct 2026 · Ref RTDA/2026/014')).toBeInTheDocument();
  expect(list.getByText('Won by Kigali Roads Ltd at FRW 6,120,000')).toBeInTheDocument();

  const toggle = list.getByRole('button', { name: AWARDS_COPY.showBidders(3) });
  expect(toggle).toHaveAttribute('aria-expanded', 'false');
  const bidders = document.getElementById(toggle.getAttribute('aria-controls')!)!;
  expect(bidders).not.toBeVisible();
  fireEvent.click(toggle);
  expect(toggle).toHaveAttribute('aria-expanded', 'true');
  expect(toggle).toHaveTextContent(AWARDS_COPY.hideBidders(3));
  expect(bidders).toBeVisible();
  expect(within(bidders).getAllByRole('listitem').map((li) => li.textContent)).toEqual([
    'Kigali Roads Ltd — FRW 6,120,000 (winner)',
    'Hills Construction — FRW 7,400,000',
    'Lake Works — price not published',
  ]);

  const notice = list.getByRole('link', { name: AWARDS_COPY.noticeLabel(AWARD.title) });
  expect(notice).toHaveTextContent(AWARDS_COPY.notice);
  expect(notice).toHaveAttribute('href', AWARD.url);
  expect(notice).toHaveAttribute('target', '_blank');
  expect(notice).toHaveAttribute('rel', 'noopener noreferrer');
  expect(screen.getByRole('link', { name: AWARDS_COPY.back })).toHaveAttribute('href', '/benchmarks');
});

test('awards page through with limit and offset; unsafe links and missing parts are left out', async () => {
  const page = (n: number) => Array.from({ length: n }, (_, i) => ({ ...AWARD, id: `a${i}`, title: `Award ${i}`, bidders: [], winner: null, url: 'javascript:alert(1)' }));
  const api = mockApi({
    'GET /me': ME,
    'GET /api/benchmarks': { categories: CATEGORIES },
    'GET /api/benchmarks/road-works': (_b: unknown, url: string) => (url.includes('offset=20') ? { awards: page(3), total: 23 } : { awards: page(20), total: 23 }),
  });
  const router = renderAt('/benchmarks/road-works');
  const list = within(await screen.findByRole('region', { name: AWARDS_COPY.listLabel }));
  expect(list.getByText('Awards 1–20 of 23')).toBeInTheDocument();
  expect(list.getAllByText(AWARDS_COPY.noBidders)).toHaveLength(20);
  expect(list.getAllByText('Winning price FRW 6,120,000')).toHaveLength(20);
  expect(list.queryByRole('link')).toBeNull();
  expect(screen.queryByRole('button', { name: AWARDS_COPY.previous })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: AWARDS_COPY.next }));
  expect(await screen.findByText('Awards 21–23 of 23')).toBeInTheDocument();
  expect(router.state.location.search).toBe('?page=2');
  expect(api.fetch.mock.calls.map((c) => c[0])).toContain('/api/benchmarks/road-works?limit=20&offset=20');
  expect(screen.queryByRole('button', { name: AWARDS_COPY.next })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: AWARDS_COPY.previous }));
  expect(await screen.findByText('Awards 1–20 of 23')).toBeInTheDocument();
});

test('an unknown category without awards: a label from its name and the empty card', async () => {
  mockApi({ 'GET /me': ME, 'GET /api/benchmarks': { categories: [] }, 'GET /api/benchmarks/cleaning-services': { awards: [] } });
  renderAt('/benchmarks/cleaning-services');
  expect(await screen.findByRole('heading', { level: 1, name: 'Cleaning services' })).toBeInTheDocument();
  expect(await screen.findByText(AWARDS_COPY.emptyTitle)).toBeInTheDocument();
});

test('phone: the same screens in the phone frame, under More', async () => {
  setViewport('phone');
  mockApi({ 'GET /me': ME, 'GET /api/benchmarks': { categories: CATEGORIES } });
  renderAt('/benchmarks');
  expect(await screen.findByRole('region', { name: BENCHMARKS_COPY.listLabel })).toBeInTheDocument();
  const tabs = screen.getByRole('navigation', { name: 'Main' });
  expect(within(tabs).getByRole('link', { name: 'More' })).toHaveAttribute('aria-current', 'page');
});
