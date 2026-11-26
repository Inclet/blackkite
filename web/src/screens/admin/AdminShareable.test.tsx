import { fireEvent, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { mockApi, status } from '../../test/mockApi';
import { renderAt, setViewport } from '../feed/testUtils';
import { SHAREABLE_COPY } from './AdminShareable';
import { ADMIN_ME } from './testData';

beforeEach(() => setViewport('desktop'));
afterEach(() => vi.unstubAllGlobals());

const item = (id: string, title: string) => ({
  id,
  stream: 'tender',
  title,
  organisation: 'Kigali Bus',
  status: 'open',
  verification: 'unverified',
  trust: 'unconfirmed',
  needsReview: false,
  reviewReasons: [],
  deadline: '2026-12-10',
  memberVisible: false,
  sources: [],
  createdAt: '2026-11-24T08:00:00Z',
  updatedAt: '2026-11-24T08:00:00Z',
  visibility: 'private',
  shareConsent: true,
});

test('lists consenting private items; Make public; a 409 is a plain sentence', async () => {
  const api = mockApi({
    'GET /me': ADMIN_ME,
    'GET /api/admin/catalogue': { total: 2, items: [item('a', 'Fuel supply'), item('b', 'Market stalls')] },
    'POST /api/admin/catalogue/a/publish': {},
    'POST /api/admin/catalogue/b/publish': status(409, { detail: 'no consent' }),
  });
  renderAt('/admin/shareable');
  const card = within(await screen.findByRole('region', { name: 'Fuel supply' }));
  expect(api.fetch.mock.calls.some(([u]) => u === '/api/admin/catalogue?shareable=true')).toBe(true);
  expect(card.getByText(SHAREABLE_COPY.date('2026-12-10'))).toHaveTextContent('Date 10 Dec 2026');
  fireEvent.click(card.getByRole('button', { name: `${SHAREABLE_COPY.publish}: Fuel supply` }));
  expect(await screen.findByText(SHAREABLE_COPY.published('Fuel supply'))).toBeInTheDocument();
  expect(screen.queryByRole('region', { name: 'Fuel supply' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: `${SHAREABLE_COPY.publish}: Market stalls` }));
  expect(await screen.findByText(`Market stalls: ${SHAREABLE_COPY.noConsent}`)).toBeInTheDocument();
  expect(await screen.findByText(SHAREABLE_COPY.none)).toBeInTheDocument();
});

test('unreachable: nothing changed', async () => {
  mockApi({ 'GET /me': ADMIN_ME, 'GET /api/admin/catalogue': { total: 1, items: [item('a', 'Fuel supply')] }, 'POST /api/admin/catalogue/a/publish': status(502) });
  renderAt('/admin/shareable');
  fireEvent.click(await screen.findByRole('button', { name: `${SHAREABLE_COPY.publish}: Fuel supply` }));
  expect(await screen.findByText(SHAREABLE_COPY.unreachable)).toBeInTheDocument();
  expect(screen.getByRole('region', { name: 'Fuel supply' })).toBeInTheDocument();
});
