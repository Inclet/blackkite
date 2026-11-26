import { fireEvent, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { referenceItems } from '../../fixtures/reference';
import { setNowForTests } from '../../lib/now';
import { mockApi } from '../../test/mockApi';
import { noSourcesText, SECTIONS_COPY } from './DetailSections';
import { renderAt, setViewport } from './testUtils';

beforeEach(() => setNowForTests('2026-11-24T14:00:00+02:00'));
afterEach(() => {
  setNowForTests(null);
  vi.unstubAllGlobals();
});

const EXTRAS = {
  fields: [
    { name: 'deadlineAt', value: '2026-11-30T17:00:00+02:00', snippet: 'Closing date: 30 November 2026, 17:00 Kigali time' },
    { name: 'valueAmount', value: 120000000, snippet: 'estimated at FRW 120,000,000' },
    { name: 'requirements', value: ['Proof of owned vehicles'], snippets: ['logbooks in the bidder’s name'] },
  ],
  sources: [
    { name: 'Job in Rwanda, tenders', url: 'https://www.jobinrwanda.com/jobs/tender', isOriginal: false, firstSeen: '2026-11-09T06:00:00Z', lastSeen: '2026-11-24T06:00:00Z' },
    { name: 'Bad link', url: 'javascript:alert(1)', isOriginal: false, firstSeen: '2026-11-10T06:00:00Z', lastSeen: '2026-11-10T06:00:00Z' },
  ],
  documents: [{ name: 'wfp-logistics-rfp.pdf' }],
  changes: [{ field: 'deadline_at', old: '2026-11-28T17:00:00+02:00', new: '2026-11-30T17:00:00+02:00', at: '2026-11-20T06:00:00Z' }],
  note: null,
  state: 'unseen',
};

function setup(extras: Record<string, unknown> = EXTRAS, role = 'member') {
  const items = referenceItems().map((i) => ({ ...i, state: 'unseen', provisional: false }));
  const wfp = items.find((i) => i.id === 'wfp-logistics')!;
  mockApi({
    'GET /api/feed': { user: { name: 'Clet' }, sources: { checked: 3, when: 'today' }, digest: { channel: 'email' }, items },
    'GET /api/shortlist': [],
    'GET /api/profiles': [{ id: 'p1' }],
    'GET /me': { id: 'u', email: 'c@x.rw', name: 'Clet', role },
    'GET /api/opportunities/wfp-logistics': { ...wfp, detail: { ...wfp.detail, ...extras } },
  });
}

test('desktop pane: the four sections, open, with quotes, sources, documents and history in words', async () => {
  setViewport('desktop');
  setup();
  renderAt('/o/wfp-logistics');
  const pane = await screen.findByRole('article');
  const details = within(await within(pane).findByRole('region', { name: SECTIONS_COPY.details }));
  expect(within(pane).getByRole('heading', { level: 3, name: SECTIONS_COPY.details })).toBeInTheDocument();
  const deadline = details.getByText('Deadline').closest('div')!;
  expect(deadline).toHaveTextContent('30 Nov 2026, 5pm — from the notice: “Closing date: 30 November 2026, 17:00 Kigali time”'.replace(/[“”]/g, ''));
  expect(deadline.querySelector('q')).toHaveTextContent('Closing date: 30 November 2026, 17:00 Kigali time');
  expect(details.getByText('FRW 120,000,000')).toBeInTheDocument();
  expect(details.getByText('Proof of owned vehicles')).toBeInTheDocument();

  const sources = within(within(pane).getByRole('region', { name: SECTIONS_COPY.sources }));
  const link = sources.getByRole('link', { name: SECTIONS_COPY.open('Job in Rwanda, tenders') });
  expect(link).toHaveAttribute('href', 'https://www.jobinrwanda.com/jobs/tender');
  expect(link).toHaveAttribute('target', '_blank');
  expect(sources.getByText('Bad link').closest('a')).toBeNull();
  expect(sources.getByText('First seen 9 Nov 2026 · last seen 24 Nov 2026')).toBeInTheDocument();
  expect(sources.getByText(SECTIONS_COPY.noOriginal)).toBeInTheDocument();

  expect(within(pane).getByRole('region', { name: SECTIONS_COPY.documents })).toHaveTextContent('wfp-logistics-rfp.pdf');
  expect(within(pane).getByRole('region', { name: SECTIONS_COPY.history })).toHaveTextContent('20 Nov 2026: the deadline moved from 28 Nov 2026, 5pm to 30 Nov 2026, 5pm.');
  expect(within(pane).queryByRole('button', { name: /Details/ })).toBeNull();
});

test('phone page: each section closed behind a real button', async () => {
  setViewport('phone');
  setup();
  renderAt('/o/wfp-logistics');
  const toggle = await screen.findByRole('button', { name: /^Details/ });
  expect(toggle).toHaveAttribute('aria-expanded', 'false');
  expect(screen.queryByText('FRW 120,000,000')).not.toBeVisible();
  fireEvent.click(toggle);
  expect(toggle).toHaveAttribute('aria-expanded', 'true');
  expect(screen.getByText('FRW 120,000,000')).toBeVisible();
  expect(screen.getByRole('heading', { level: 2, name: /^History/ })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /^Sources/ })).toHaveAttribute('aria-expanded', 'false');
});

test('fixtures show no sections', () => {
  setViewport('desktop');
  mockApi({});
  renderAt('/o/wfp-logistics?fixture=reference');
  expect(screen.queryByRole('region', { name: SECTIONS_COPY.details })).toBeNull();
});

const NO_SOURCES = { ...EXTRAS, sources: [] };

test.each([
  ['the owner', { ...NO_SOURCES, isManual: true, ownItem: { shareConsent: true, published: true } }, 'member', SECTIONS_COPY.noSourcesOwn],
  ['another member', { ...NO_SOURCES, isManual: true }, 'member', SECTIONS_COPY.noSourcesManual],
  ['an admin', { ...NO_SOURCES, isManual: true }, 'admin', SECTIONS_COPY.noSourcesManual],
  ['anyone, on an item not added by hand', NO_SOURCES, 'member', SECTIONS_COPY.noSources],
])('no sources, seen by %s', async (_who, extras, role, words) => {
  setViewport('desktop');
  setup(extras, role);
  renderAt('/o/wfp-logistics');
  const sources = await screen.findByRole('region', { name: SECTIONS_COPY.sources });
  expect(sources).toHaveTextContent(words);
  for (const other of [SECTIONS_COPY.noSourcesOwn, SECTIONS_COPY.noSourcesManual, SECTIONS_COPY.noSources].filter((w) => w !== words)) {
    expect(sources).not.toHaveTextContent(other);
  }
});

test('"You added it yourself" needs ownItem, never isManual alone', () => {
  const detail = { ...referenceItems()[0]!.detail, ...NO_SOURCES } as unknown as Parameters<typeof noSourcesText>[0];
  expect(noSourcesText({ ...detail, isManual: true })).toBe(SECTIONS_COPY.noSourcesManual);
  expect(noSourcesText({ ...detail, ownItem: { shareConsent: false, published: false } })).toBe(SECTIONS_COPY.noSourcesOwn);
  expect(noSourcesText(detail)).toBe(SECTIONS_COPY.noSources);
});
