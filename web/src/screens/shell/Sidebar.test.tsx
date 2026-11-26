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
const MEMBER = { ...ME, role: 'member' };
const BOARD = ['Feed', 'Shortlist', 'Calendar', 'Sources', 'Profiles'];
/** Live sessions add Benchmarks after the board's five (never on fixtures). */
const LIVE = [...BOARD, 'Benchmarks'];

function sidebar() {
  const nav = screen.getByRole('navigation', { name: 'Main' });
  return {
    items: within(nav).getAllByRole('link').map((l) => l.textContent),
    current: within(nav).queryAllByRole('link').find((l) => l.getAttribute('aria-current') === 'page')?.textContent ?? null,
    text: nav.textContent,
  };
}

test.each([
  ['/?fixture=reference', 'Feed', BOARD],
  ['/shortlist', 'Shortlist', LIVE],
  ['/calendar', 'Calendar', LIVE],
  ['/sources', 'Sources', LIVE],
  ['/profiles', 'Profiles', LIVE],
  ['/profiles/p1', 'Profiles', LIVE],
  ['/settings/digest', 'Profiles', LIVE],
  ['/account', 'Profiles', LIVE],
  ['/more', null, LIVE],
  ['/benchmarks', 'Benchmarks', LIVE],
  ['/benchmarks/road-works', 'Benchmarks', LIVE],
])('%s: the feed board\'s five items (plus Benchmarks when live) and the "Next digest" footer, %s current (a member)', async (url, current, items) => {
  mockApi({
    'GET /me': MEMBER,
    'GET /api/shortlist': [],
    'GET /api/profiles': [],
    'GET /api/profiles/p1': {},
    'GET /api/digest-settings': { channel: 'email', frequency: 'weekly', day: 'mon', alertMinFit: null, streams: null },
  });
  renderAt(url);
  await waitFor(() => expect(screen.getByRole('navigation', { name: 'Main' })).toBeInTheDocument());
  const s = sidebar();
  expect(s.items).toEqual(items);
  expect(s.current).toBe(current);
  expect(s.text).toContain('Next digestMonday 30 November, by email');
});

test('a live admin session adds "Admin" after the board\'s five items; the fixture feed never does', async () => {
  mockApi({ 'GET /me': ME, 'GET /api/shortlist': [] });
  renderAt('/shortlist');
  await waitFor(() => expect(sidebar().items).toEqual([...LIVE, 'Admin']));
  expect(within(screen.getByRole('navigation', { name: 'Main' })).getByRole('link', { name: 'Admin' })).toHaveAttribute('href', '/admin');
  expect(sidebarCurrent('/admin/sources/3')).toBe('/admin');
  expect(sidebarCurrent('/admin')).toBe('/admin');
});

test('the fixture feed keeps the board\'s sidebar even for an admin, and asks nobody', async () => {
  const api = mockApi({ 'GET /me': ME });
  renderAt('/?fixture=reference');
  await waitFor(() => expect(screen.getByRole('navigation', { name: 'Main' })).toBeInTheDocument());
  await new Promise((r) => setTimeout(r, 20));
  expect(sidebar().items).toEqual(BOARD);
  expect(api.calls).toEqual([]);
});

test('phone More lists Benchmarks for everyone', async () => {
  setViewport('phone');
  mockApi({ 'GET /me': MEMBER });
  renderAt('/more');
  const more = within(await screen.findByRole('region', { name: 'More' }));
  expect(more.getByRole('link', { name: 'Benchmarks' })).toHaveAttribute('href', '/benchmarks');
  expect(MORE_LINKS.map((l) => l.label)).toEqual(['Profiles', 'Digest', 'Sources', 'Benchmarks', 'Account']);
});

test('phone More: Admin only for admins', async () => {
  setViewport('phone');
  mockApi({ 'GET /me': MEMBER });
  renderAt('/more');
  const more = within(await screen.findByRole('region', { name: 'More' }));
  await new Promise((r) => setTimeout(r, 20));
  expect(more.queryByRole('link', { name: 'Admin' })).toBeNull();
  mockApi({ 'GET /me': ME });
  renderAt('/more');
  expect(await screen.findByRole('link', { name: 'Admin' })).toHaveAttribute('href', '/admin');
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
