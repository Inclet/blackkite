import { screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { referenceItems } from '../../fixtures/reference';
import { setNowForTests } from '../../lib/now';
import { mockApi } from '../../test/mockApi';
import { DETAIL_COPY } from './parts';
import { renderAt, setViewport } from './testUtils';

beforeEach(() => setNowForTests('2026-11-24T14:00:00+02:00'));
afterEach(() => {
  setNowForTests(null);
  vi.unstubAllGlobals();
});

const EMPTY = { fields: [], sources: [], documents: [], changes: [], note: null, state: 'unseen' };

/** The WFP row as a manual item: `row` goes on the feed item's detail, `extras` on the detail answer. */
function setup(row: Record<string, unknown>, extras: Record<string, unknown>) {
  const items = referenceItems().map((i) => ({ ...i, state: 'unseen', provisional: false }));
  const wfp = items.find((i) => i.id === 'wfp-logistics')!;
  wfp.detail = { ...wfp.detail, originalUrl: 'https://example.rw/tip', ...row };
  mockApi({
    'GET /api/feed': { user: { name: 'Clet' }, sources: { checked: 3, when: 'today' }, digest: { channel: 'email' }, items },
    'GET /api/shortlist': [],
    'GET /api/profiles': [{ id: 'p1' }],
    'GET /me': { id: 'u', email: 'c@x.rw', name: 'Clet', role: 'member' },
    'GET /api/opportunities/wfp-logistics': { ...wfp, detail: { ...wfp.detail, ...EMPTY, ...extras } },
  });
}

const OWNER = [{ isManual: true }, { isManual: true, ownItem: { shareConsent: false, published: false } }] as const;

test.each([
  ['desktop', 'the owner', ...OWNER, DETAIL_COPY.ownLink],
  ['desktop', 'another member', { isManual: true }, { isManual: true }, DETAIL_COPY.manualLink],
  ['desktop', 'another member, isManual only on the detail answer', {}, { isManual: true }, DETAIL_COPY.manualLink],
  ['desktop', 'anyone, on a collected item', {}, {}, 'Read the original'],
  ['phone', 'the owner', ...OWNER, DETAIL_COPY.ownLink],
  ['phone', 'another member', { isManual: true }, { isManual: true }, DETAIL_COPY.manualLink],
  ['phone', 'anyone, on a collected item', {}, {}, 'Read the original notice'],
] as const)('%s: the link out, seen by %s', async (viewport, _who, row, extras, words) => {
  setViewport(viewport);
  setup(row, extras);
  renderAt('/o/wfp-logistics');
  const scope = viewport === 'desktop' ? within(await screen.findByRole('article')) : screen;
  await waitFor(() => expect(scope.getByRole('link', { name: words })).toHaveAttribute('href', 'https://example.rw/tip'));
  for (const other of [DETAIL_COPY.ownLink, DETAIL_COPY.manualLink]) if (other !== words) expect(scope.queryByRole('link', { name: other })).toBeNull();
});

test('fixtures keep the board words', () => {
  setViewport('desktop');
  mockApi({});
  renderAt('/o/wfp-logistics?fixture=reference');
  expect(within(screen.getByRole('article')).getByRole('link', { name: 'Read the original' })).toBeInTheDocument();
});
