import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { referenceItems } from '../../fixtures/reference';
import { setNowForTests } from '../../lib/now';
import { mockApi, status } from '../../test/mockApi';
import { DISMISS_COPY } from './model';
import { renderAt, setViewport } from './testUtils';

beforeEach(() => {
  setNowForTests('2026-11-24T14:00:00+02:00');
  setViewport('desktop');
});
afterEach(() => {
  setNowForTests(null);
  vi.unstubAllGlobals();
});

const LABELS = ['Not my sector', 'Too small', "Can't meet the requirements", 'Already knew about it', 'Other'];
const press = (key: string) => act(() => void fireEvent.keyDown(window, { key }));
const prompt = () => screen.queryByRole('region', { name: new RegExp(`^${DISMISS_COPY.question.replace(/[()?]/g, '\\$&')}`) });
const chips = () => within(within(prompt()!).getByRole('group', { name: DISMISS_COPY.question })).getAllByRole('button');
const announcer = () => document.querySelector('[aria-live="polite"]');
const rowTitles = () => within(screen.getByRole('region', { name: 'Opportunities' })).getAllByRole('link').map((l) => l.textContent ?? '');

function liveApi(overrides: Record<string, unknown> = {}) {
  return mockApi({
    'GET /api/feed': { user: { name: 'Clet' }, sources: { checked: 3, when: 'this morning' }, digest: { channel: 'email' }, items: referenceItems().map((i) => ({ ...i, state: 'unseen', provisional: false })) },
    'GET /api/shortlist': [],
    'GET /api/profiles': [{ id: 'p1', name: 'Ironji-Trade', type: 'business', data: {}, version: 1, active: true }],
    'GET /me': { id: 'u', email: 'c@x.rw', name: 'Clet', role: 'admin' },
    'GET /api/opportunities/abh-summit': () => new Promise(() => {}),
    'GET /api/opportunities/wfp-logistics': () => new Promise(() => {}),
    'PUT /api/opportunities/wfp-logistics/state': {},
    ...overrides,
  });
}

const puts = (api: ReturnType<typeof mockApi>) => api.calls.filter((c) => c.key.startsWith('PUT ')).map((c) => [c.key, c.body]);

test('no prompt until something is dismissed (the boards never show one)', () => {
  renderAt('/?fixture=reference');
  expect(prompt()).toBeNull();
  expect(screen.queryByText(DISMISS_COPY.question)).toBeNull();
});

test('"Not for me": dismissed at once, then "Why not? (optional)" with the five reasons as chips', () => {
  renderAt('/?fixture=reference');
  fireEvent.click(within(screen.getByRole('article')).getByRole('button', { name: 'Not for me' }));
  expect(rowTitles().some((t) => t.includes('Logistics, transport'))).toBe(false);
  expect(prompt()).toHaveAccessibleName(`${DISMISS_COPY.question}: Logistics, transport and warehousing support`);
  expect(chips().map((c) => c.textContent)).toEqual(LABELS);
  for (const c of chips()) {
    expect(c).toHaveAttribute('type', 'button');
    // One-shot actions, not toggles.
    expect(c).not.toHaveAttribute('aria-pressed');
  }
});

test('desktop "Not for me" button: focus moves to the first reason chip; a choice returns it to the selected row', () => {
  renderAt('/?fixture=reference');
  const button = within(screen.getByRole('article')).getByRole('button', { name: 'Not for me' });
  button.focus();
  fireEvent.click(button);
  expect(document.activeElement).toBe(chips()[0]);
  expect(document.activeElement).toHaveTextContent('Not my sector');
  fireEvent.click(chips()[0]!);
  expect(prompt()).toBeNull();
  expect(document.activeElement).toHaveTextContent('ABH Summit');
});

test('desktop X: focus stays on the list (not moved to the prompt), so J/K/S/X carry on', () => {
  renderAt('/?fixture=reference');
  within(screen.getByRole('region', { name: 'Opportunities' })).getAllByRole('link')[0]!.focus();
  press('x');
  expect(prompt()).not.toBeNull();
  expect(document.activeElement).toHaveTextContent('ABH Summit');
  expect(document.activeElement!.closest('section')).not.toBe(prompt());
});

test('J from a focused chip closes the prompt and focus follows the selection, not the page', () => {
  const router = renderAt('/?fixture=reference');
  fireEvent.click(within(screen.getByRole('article')).getByRole('button', { name: 'Not for me' }));
  expect(document.activeElement).toBe(chips()[0]);
  press('j');
  expect(prompt()).toBeNull();
  const id = router.state.location.pathname.replace('/o/', '');
  expect(document.activeElement).toHaveAttribute('id', `row-${id}`);
});

test('the announcement after a dismiss names the item and the optional prompt', () => {
  renderAt('/?fixture=reference');
  press('x');
  expect(announcer()).toHaveTextContent(`Marked not for me: Logistics, transport and warehousing support. ${DISMISS_COPY.ask}`);
});

test('X: the prompt survives the move to the next item; J (the next navigation) closes it', () => {
  const router = renderAt('/?fixture=reference');
  press('x');
  expect(prompt()).not.toBeNull();
  expect(router.state.location.pathname).toBe('/o/abh-summit');
  press('j');
  expect(prompt()).toBeNull();
});

test('J/K/S/X still work with focus on a chip', () => {
  const router = renderAt('/?fixture=reference');
  press('x');
  chips()[0]!.focus();
  press('s');
  expect(within(screen.getByRole('article')).getByRole('button', { name: 'Save to shortlist' })).toHaveAttribute('aria-pressed', 'true');
  press('x');
  // The second dismissal asks about the newer item.
  expect(prompt()).toHaveAccessibleName(`${DISMISS_COPY.question}: ABH Summit and Grand Finale`);
  chips()[1]!.focus();
  const before = router.state.location.pathname;
  press('j');
  expect(router.state.location.pathname).not.toBe(before);
  expect(prompt()).toBeNull();
});

test('live: choosing a reason PUTs it, closes the prompt and returns focus to the selected row', async () => {
  const api = liveApi();
  renderAt('/');
  await screen.findByRole('article');
  await act(async () => {});
  press('x');
  // Let the dismissal reach the server first: the live feed then drops the item.
  await waitFor(() => expect(puts(api)).toHaveLength(1));
  await act(async () => {});
  fireEvent.click(screen.getByRole('button', { name: 'Too small' }));
  expect(prompt()).toBeNull();
  expect(document.activeElement).toHaveTextContent('ABH Summit');
  await waitFor(() =>
    expect(puts(api)).toEqual([
      ['PUT /api/opportunities/wfp-logistics/state', { state: 'dismissed' }],
      ['PUT /api/opportunities/wfp-logistics/state', { state: 'dismissed', dismissReason: 'too_small' }],
    ]),
  );
  expect(announcer()).toHaveTextContent(DISMISS_COPY.noted);
});

test.each([
  [0, 'not_my_sector'],
  [1, 'too_small'],
  [2, 'cant_meet_requirements'],
  [3, 'already_knew'],
  [4, 'other'],
])('live: chip %i sends %s', async (i, code) => {
  const api = liveApi();
  renderAt('/');
  await screen.findByRole('article');
  await act(async () => {});
  press('x');
  fireEvent.click(chips()[i]!);
  await waitFor(() => expect(puts(api).at(-1)).toEqual(['PUT /api/opportunities/wfp-logistics/state', { state: 'dismissed', dismissReason: code }]));
});

test('live: a reason that cannot be saved says so; the item stays dismissed', async () => {
  let n = 0;
  liveApi({ 'PUT /api/opportunities/wfp-logistics/state': () => (++n === 1 ? {} : status(502)) });
  renderAt('/');
  await screen.findByRole('article');
  await act(async () => {});
  press('x');
  fireEvent.click(screen.getByRole('button', { name: 'Other' }));
  await waitFor(() => expect(announcer()).toHaveTextContent(DISMISS_COPY.reasonFailed));
  expect(rowTitles().some((t) => t.includes('Logistics, transport'))).toBe(false);
});

test('phone: "Not for me" on the opportunity page; the prompt waits on the feed; opening an item closes it', () => {
  setViewport('phone');
  renderAt('/o/wfp-logistics?fixture=reference');
  fireEvent.click(screen.getByRole('button', { name: 'Not for me' }));
  expect(prompt()).not.toBeNull();
  expect(chips().map((c) => c.textContent)).toEqual(LABELS);
  // Focus went to the next row, not the prompt (J/K carry on from there).
  expect(document.activeElement).toHaveTextContent('ABH Summit');
  fireEvent.click(screen.getByRole('link', { name: /ABH Summit/ }));
  fireEvent.click(screen.getByRole('link', { name: 'Feed' }));
  expect(prompt()).toBeNull();
});

test('phone: X on a focused row shows the prompt; a choice closes it', () => {
  setViewport('phone');
  renderAt('/?fixture=reference');
  within(screen.getByRole('region', { name: 'Opportunities' })).getAllByRole('link')[0]!.focus();
  press('x');
  expect(prompt()).not.toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Already knew about it' }));
  expect(prompt()).toBeNull();
  expect(document.activeElement).toHaveTextContent('ABH Summit');
});
