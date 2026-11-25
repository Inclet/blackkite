import { screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { setNowForTests } from '../../lib/now';
import { mockApi } from '../../test/mockApi';
import { renderAt, setViewport } from '../feed/testUtils';
import { MORE_LINKS } from '../settings/More';
import { PROFILE_SETTINGS_LINKS } from '../profiles/Profiles';
import { sidebarCurrent } from './AppShell';
import { SIDEBAR_NAV } from './Sidebar';

beforeEach(() => {
  setNowForTests('2026-11-24T14:00:00+02:00');
  setViewport('desktop');
});
afterEach(() => {
  setNowForTests(null);
  vi.unstubAllGlobals();
});

const ME = { id: 'u', email: 'c@x.rw', name: 'Clet', role: 'admin' };
const BOARD = ['Feed', 'Shortlist', 'Calendar', 'Sources', 'Profiles'];

function sidebar() {
  const nav = screen.getByRole('navigation', { name: 'Main' });
  return {
    items: within(nav).getAllByRole('link').map((l) => l.textContent),
    current: within(nav).queryAllByRole('link').find((l) => l.getAttribute('aria-current') === 'page')?.textContent ?? null,
    text: nav.textContent,
  };
}

test.each([
  ['/?fixture=reference', 'Feed'],
  ['/shortlist', 'Shortlist'],
  ['/calendar', 'Calendar'],
  ['/sources', 'Sources'],
  ['/profiles', 'Profiles'],
  ['/profiles/p1', 'Profiles'],
  ['/settings/digest', 'Profiles'],
  ['/account', 'Profiles'],
  ['/more', null],
])('%s: the feed board\'s five items and the "Next digest" footer, %s current', async (url, current) => {
  mockApi({
    'GET /me': ME,
    'GET /api/shortlist': [],
    'GET /api/profiles': [],
    'GET /api/profiles/p1': {},
    'GET /api/digest-settings': { channel: 'email', frequency: 'weekly', day: 'mon', alertMinFit: null, streams: null },
  });
  renderAt(url);
  await waitFor(() => expect(screen.getByRole('navigation', { name: 'Main' })).toBeInTheDocument());
  const s = sidebar();
  expect(s.items).toEqual(BOARD);
  expect(s.current).toBe(current);
  expect(s.text).toContain('Next digestMonday 30 November, by email');
});

test('SIDEBAR_NAV is the board\'s list; Digest and Account are not on it', () => {
  expect(SIDEBAR_NAV.map((n) => n.label)).toEqual(BOARD);
  expect(sidebarCurrent('/settings/digest')).toBe('/profiles');
  expect(sidebarCurrent('/account')).toBe('/profiles');
  expect(sidebarCurrent('/o/x')).toBe('/');
  expect(sidebarCurrent('/more')).toBeNull();
});

test('Profiles carries a card with Digest settings and Account; More keeps its links', async () => {
  mockApi({ 'GET /me': ME, 'GET /api/profiles': [] });
  renderAt('/profiles');
  const card = within(await screen.findByRole('region', { name: 'Settings' }));
  expect(card.getAllByRole('link').map((l) => [l.textContent, l.getAttribute('href')])).toEqual(PROFILE_SETTINGS_LINKS.map((l) => [l.label, l.to]));
  expect(PROFILE_SETTINGS_LINKS.map((l) => l.label)).toEqual(['Digest settings', 'Account']);
  expect(MORE_LINKS.map((l) => l.to)).toEqual(expect.arrayContaining(['/settings/digest', '/account']));
});

test('phone Profiles shows the same settings card', async () => {
  setViewport('phone');
  mockApi({ 'GET /me': ME, 'GET /api/profiles': [] });
  renderAt('/profiles');
  expect(await screen.findByRole('region', { name: 'Settings' })).toBeInTheDocument();
});
