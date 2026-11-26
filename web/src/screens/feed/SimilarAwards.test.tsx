import { fireEvent, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { referenceItems } from '../../fixtures/reference';
import { setNowForTests } from '../../lib/now';
import { mockApi } from '../../test/mockApi';
import { SIMILAR_COPY } from './SimilarAwards';
import { renderAt, setViewport } from './testUtils';

beforeEach(() => setNowForTests('2026-11-24T14:00:00+02:00'));
afterEach(() => {
  setNowForTests(null);
  vi.unstubAllGlobals();
});

const BENCHMARK = { category: 'freight', median: 6100000, p25: 4200000, p75: 9800000, awards: 14, currency: 'RWF' };
const SENTENCE = 'Half of similar contracts were awarded between FRW 4.2M and FRW 9.8M (14 awards).';
const EXTRAS = { fields: [], sources: [], documents: [], changes: [], note: null, state: 'unseen' };

function setup(id: string, benchmark: unknown) {
  const items = referenceItems().map((i) => ({ ...i, state: 'unseen', provisional: false, detail: { ...i.detail, isManual: false } }));
  const item = items.find((i) => i.id === id)!;
  return mockApi({
    'GET /api/feed': { user: { name: 'Clet' }, sources: { checked: 3, when: 'today' }, digest: { channel: 'email' }, items },
    'GET /api/shortlist': [],
    'GET /api/profiles': [{ id: 'p1' }],
    'GET /me': { id: 'u', email: 'c@x.rw', name: 'Clet', role: 'member' },
    [`GET /api/opportunities/${id}`]: { ...item, detail: { ...item.detail, ...EXTRAS, ...(benchmark ? { benchmark } : {}) } },
    'GET /api/benchmarks': { categories: [] },
    'GET /api/benchmarks/freight': { awards: [] },
  });
}

test('desktop pane: a tender with a benchmark says what similar contracts went for, linking to the category', async () => {
  setViewport('desktop');
  setup('wfp-logistics', BENCHMARK);
  const router = renderAt('/o/wfp-logistics');
  const pane = within(await screen.findByRole('article'));
  expect(await pane.findByText(SIMILAR_COPY.heading)).toBeInTheDocument();
  const link = pane.getByRole('link', { name: SENTENCE });
  expect(link).toHaveAttribute('href', '/benchmarks/freight');
  fireEvent.click(link);
  expect(router.state.location.pathname).toBe('/benchmarks/freight');
});

test('phone page: the same line', async () => {
  setViewport('phone');
  setup('wfp-logistics', BENCHMARK);
  renderAt('/o/wfp-logistics');
  expect(await screen.findByRole('link', { name: SENTENCE })).toHaveAttribute('href', '/benchmarks/freight');
});

test('no benchmark, or too few awards: no line', async () => {
  setViewport('desktop');
  setup('wfp-logistics', null);
  renderAt('/o/wfp-logistics');
  await screen.findByRole('article');
  await new Promise((r) => setTimeout(r, 20));
  expect(screen.queryByText(SIMILAR_COPY.heading)).toBeNull();

  setup('wfp-logistics', { ...BENCHMARK, awards: 2 });
  renderAt('/o/wfp-logistics');
  await screen.findAllByRole('article');
  await new Promise((r) => setTimeout(r, 20));
  expect(screen.queryByText(SIMILAR_COPY.heading)).toBeNull();
});

test('the fixture boards never show it', async () => {
  setViewport('desktop');
  renderAt('/o/wfp-logistics?fixture=reference');
  await screen.findByRole('article');
  expect(screen.queryByText(SIMILAR_COPY.heading)).toBeNull();
});
