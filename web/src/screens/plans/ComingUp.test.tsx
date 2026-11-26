import { fireEvent, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { setNowForTests } from '../../lib/now';
import { mockApi, status } from '../../test/mockApi';
import { renderAt, setViewport } from '../feed/testUtils';
import { COMING_UP_COPY, planFacts } from './ComingUp';

const ME = { id: 'u', email: 'c@x.rw', name: 'Clet', role: 'member' };

/** As GET /api/plans sends it (contract section 6). */
const PLANS = {
  items: [
    {
      id: 'pl1',
      entity: 'Rwanda Agriculture Board',
      description: 'Cold-chain transport of vaccines and seed to district stores',
      method: 'open_competitive_bidding',
      estimatedValue: '45000000.00',
      currency: 'RWF',
      plannedFor: '2027-Q1',
      matchedProfile: 'Ironji-Trade',
      url: 'https://www.umucyo.gov.rw/plans/rab-2026',
    },
    { id: 'pl2', entity: 'City of Kigali', description: 'Data platform for waste collection', method: null, plannedFor: '2027-03', matchedProfile: 'AI lab', url: 'ftp://x' },
  ],
};

const CALENDAR = { days: [] };
const LINK = { url: 'https://blackkite.example/c.ics', webcalUrl: 'webcal://blackkite.example/c.ics', rotatedAt: null };

beforeEach(() => {
  setNowForTests('2026-11-24T14:00:00+02:00');
  setViewport('desktop');
});
afterEach(() => {
  setNowForTests(null);
  vi.unstubAllGlobals();
});

test('the facts line: method, estimated value when known, and when it is planned', () => {
  expect(planFacts(PLANS.items[0]!)).toBe('Open competitive bidding · Estimated FRW 45M · Planned for Q1 2027');
  expect(planFacts(PLANS.items[1]!)).toBe('Planned for March 2027');
});

test.each(['/calendar', '/shortlist'])('%s: a "Coming up" card lists planned tenders that match the profiles, with a link to the plan', async (url) => {
  mockApi({ 'GET /me': ME, 'GET /api/calendar': CALENDAR, 'GET /api/calendar/feed-link': LINK, 'GET /api/shortlist': [], 'GET /api/plans': PLANS });
  renderAt(url);
  const card = within(await screen.findByRole('region', { name: COMING_UP_COPY.title }));
  expect(card.getByRole('heading', { level: 2, name: COMING_UP_COPY.title })).toBeInTheDocument();
  expect(await card.findByText('Rwanda Agriculture Board')).toBeInTheDocument();
  expect(card.getByText('Cold-chain transport of vaccines and seed to district stores')).toBeInTheDocument();
  expect(card.getByText('Open competitive bidding · Estimated FRW 45M · Planned for Q1 2027')).toBeInTheDocument();
  expect(card.getByText('Matches Ironji-Trade')).toBeInTheDocument();
  expect(card.getByText('Matches AI lab')).toBeInTheDocument();
  const links = card.getAllByRole('link');
  // Only http(s) links are shown.
  expect(links).toHaveLength(1);
  expect(links[0]).toHaveAccessibleName(COMING_UP_COPY.planLabel('Rwanda Agriculture Board'));
  expect(links[0]).toHaveTextContent(COMING_UP_COPY.plan);
  expect(links[0]).toHaveAttribute('target', '_blank');
  expect(links[0]).toHaveAttribute('rel', 'noopener noreferrer');
});

test('nothing planned: the empty line', async () => {
  mockApi({ 'GET /me': ME, 'GET /api/calendar': CALENDAR, 'GET /api/calendar/feed-link': LINK, 'GET /api/plans': { items: [] } });
  renderAt('/calendar');
  const card = within(await screen.findByRole('region', { name: COMING_UP_COPY.title }));
  expect(await card.findByText(COMING_UP_COPY.empty)).toBeInTheDocument();
});

test('unreachable: says so in the card with Try again; the rest of the page stays', async () => {
  const api = mockApi({ 'GET /me': ME, 'GET /api/shortlist': [], 'GET /api/plans': status(503) });
  renderAt('/shortlist');
  const card = within(await screen.findByRole('region', { name: COMING_UP_COPY.title }));
  expect(await card.findByText(COMING_UP_COPY.unreachable)).toBeInTheDocument();
  api.on('GET /api/plans', PLANS);
  fireEvent.click(card.getByRole('button', { name: 'Try again' }));
  expect(await card.findByText('Rwanda Agriculture Board')).toBeInTheDocument();
});

test('phone: the card on the Calendar list', async () => {
  setViewport('phone');
  mockApi({ 'GET /me': ME, 'GET /api/calendar': CALENDAR, 'GET /api/calendar/feed-link': LINK, 'GET /api/plans': PLANS });
  renderAt('/calendar');
  expect(await screen.findByRole('region', { name: COMING_UP_COPY.title })).toBeInTheDocument();
});
