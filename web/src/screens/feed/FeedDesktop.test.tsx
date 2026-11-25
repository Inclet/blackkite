import { act, fireEvent, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { reference } from '../../fixtures/reference';
import { setNowForTests } from '../../lib/now';
import { renderAt, setViewport } from './testUtils';

beforeEach(() => {
  setNowForTests('2026-11-24T14:00:00+02:00');
  setViewport('desktop');
});
afterEach(() => {
  setNowForTests(null);
  vi.unstubAllGlobals();
});

const list = () => within(screen.getByRole('region', { name: 'Opportunities' }));
const rows = () => list().getAllByRole('link');
const current = () => rows().find((r) => r.getAttribute('aria-current') === 'true');
const pane = () => screen.getByRole('article');
const press = (key: string, init: KeyboardEventInit = {}) => act(() => void fireEvent.keyDown(window, { key, ...init }));

test('the reference feed: nav, greeting, chips, six rows, first selected, detail pane', () => {
  renderAt('/?fixture=reference');
  const nav = screen.getByRole('navigation', { name: 'Main' });
  expect(within(nav).getByRole('link', { name: 'Feed' })).toHaveAttribute('aria-current', 'page');
  expect(within(nav).getAllByRole('link').map((l) => l.textContent)).toEqual(['Feed', 'Shortlist', 'Calendar', 'Sources', 'Profiles']);
  expect(within(nav).getByText('Monday 30 November, by email')).toBeInTheDocument();
  expect(screen.getByRole('heading', { level: 1, name: 'Good afternoon, Clet' })).toBeInTheDocument();
  expect(screen.getByText('Six things worth a look. One closes in 6 days.')).toBeInTheDocument();
  expect(screen.getByText('8 sources checked this morning')).toBeInTheDocument();
  const chips = within(screen.getByRole('group', { name: 'Filter by stream' })).getAllByRole('button');
  expect(chips.map((c) => [c.textContent, c.getAttribute('aria-pressed')])).toEqual([
    ['All', 'true'],
    ['Tenders', 'false'],
    ['Investments', 'false'],
    ['Funding', 'false'],
    ['Events', 'false'],
  ]);
  expect(rows()).toHaveLength(6);
  expect(current()).toHaveTextContent('Logistics, transport and warehousing support');
  expect(list().getByText('1 to 2 Dec')).toHaveClass('outlined');
  expect(within(pane()).getByRole('heading', { level: 2, name: 'Logistics, transport and warehousing support' })).toBeInTheDocument();
  expect(screen.getByRole('article', { name: 'Logistics, transport and warehousing support' })).toBeInTheDocument();
  expect(within(pane()).getByText('World Food Programme · Kigali · closes 30 Nov')).toBeInTheDocument();
  expect(within(pane()).getByRole('button', { name: 'Save to shortlist' })).toHaveAttribute('aria-pressed', 'false');
  expect(within(pane()).getByRole('link', { name: 'Read the original' })).toHaveAttribute('href', 'https://www.jobinrwanda.com/jobs/tender');
});

test('J and K move the selection, update the pane and the URL, and stop at the ends', () => {
  const router = renderAt('/?fixture=reference');
  press('k');
  expect(current()).toHaveTextContent('Logistics');
  press('j');
  expect(current()).toHaveTextContent('ABH Summit and Grand Finale');
  expect(router.state.location.pathname).toBe('/o/abh-summit');
  expect(router.state.location.search).toBe('?fixture=reference');
  expect(within(pane()).getByRole('heading', { level: 2 })).toHaveTextContent('ABH Summit and Grand Finale');
  for (let i = 0; i < 10; i++) press('j');
  expect(current()).toHaveTextContent('Five-year treasury bond');
  press('K');
  expect(current()).toHaveTextContent('develoPPP Ventures, cohort 6');
});

/** Several keys in one tick: none of them re-render in between. */
const pressAll = (...keys: string[]) => act(() => keys.forEach((key) => fireEvent.keyDown(window, { key })));

test('J then K in the same tick returns to the starting row', () => {
  const router = renderAt('/o/abh-summit?fixture=reference');
  expect(current()).toHaveTextContent('ABH Summit');
  pressAll('j', 'k');
  expect(current()).toHaveTextContent('ABH Summit');
  expect(router.state.location.pathname).toBe('/o/abh-summit');
  pressAll('j', 'j', 'k');
  expect(rows().indexOf(current()!)).toBe(2);
});

test('X then J in the same tick moves on from the newly selected row', () => {
  renderAt('/?fixture=reference');
  const before = rows().map((r) => r.textContent);
  pressAll('x', 'j');
  // Logistics removed, ABH selected by X, then J moves to the row after ABH.
  expect(rows()).toHaveLength(5);
  expect(current()!.textContent).toBe(before[2]);
});

test('X then K in the same tick does not return to the removed row', () => {
  renderAt('/o/abh-summit?fixture=reference');
  const before = rows().map((r) => r.textContent);
  pressAll('x', 'k');
  expect(rows()).toHaveLength(5);
  expect(current()!.textContent).toBe(before[0]);
  pressAll('x', 'x');
  expect(rows()).toHaveLength(3);
});

test('S saves and unsaves the selected item', () => {
  renderAt('/?fixture=reference');
  press('s');
  // One label; aria-pressed carries the state.
  expect(within(pane()).getByRole('button', { name: 'Save to shortlist' })).toHaveAttribute('aria-pressed', 'true');
  expect(within(pane()).queryByRole('button', { name: 'Saved to shortlist' })).toBeNull();
  expect(screen.getByRole('status', { name: '' })).toHaveTextContent('Saved to shortlist: Logistics, transport and warehousing support');
  expect(rows()).toHaveLength(6);
  press('s');
  expect(within(pane()).getByRole('button', { name: 'Save to shortlist' })).toHaveAttribute('aria-pressed', 'false');
});

test('X removes the selected row and selects the next one', () => {
  const router = renderAt('/?fixture=reference');
  press('x');
  expect(rows()).toHaveLength(5);
  expect(list().queryByText('Logistics, transport and warehousing support')).toBeNull();
  expect(current()).toHaveTextContent('ABH Summit');
  expect(router.state.location.pathname).toBe('/o/abh-summit');
  expect(screen.getByText('Five things worth a look.')).toBeInTheDocument();
});

test('X on the focused row moves focus to the newly selected row', () => {
  renderAt('/?fixture=reference');
  act(() => current()!.focus());
  press('x');
  expect(current()).toHaveTextContent('ABH Summit');
  expect(document.activeElement).toBe(current());
});

test('X with focus elsewhere leaves focus where it is', () => {
  renderAt('/?fixture=reference');
  const save = within(pane()).getByRole('button', { name: 'Save to shortlist' });
  act(() => save.focus());
  press('x');
  expect(document.activeElement).toBe(within(pane()).getByRole('button', { name: 'Save to shortlist' }));
});

test('dismissing the last row moves focus to the page heading', () => {
  renderAt('/?fixture=reference');
  fireEvent.click(screen.getByRole('button', { name: 'Investments' }));
  expect(rows()).toHaveLength(1);
  act(() => current()!.focus());
  press('x');
  expect(screen.queryByRole('region', { name: 'Opportunities' })).toBeNull();
  expect(document.activeElement).toBe(screen.getByRole('heading', { level: 1 }));
});

test('the Not for me button does the same as X', () => {
  renderAt('/o/tbond-5y?fixture=reference');
  fireEvent.click(within(pane()).getByRole('button', { name: 'Not for me' }));
  expect(rows()).toHaveLength(5);
  expect(current()).toHaveTextContent('develoPPP');
});

test('keys are ignored with a modifier held or while typing', () => {
  const router = renderAt('/?fixture=reference');
  press('j', { ctrlKey: true });
  press('j', { metaKey: true });
  press('j', { altKey: true });
  press('x', { shiftKey: true });
  const input = document.createElement('input');
  document.body.appendChild(input);
  act(() => void fireEvent.keyDown(input, { key: 'j' }));
  input.remove();
  expect(current()).toHaveTextContent('Logistics');
  expect(rows()).toHaveLength(6);
  expect(router.state.location.pathname).toBe('/');
});

test('/o/:id on desktop opens the feed with that item selected', () => {
  renderAt('/o/t2s-call?fixture=reference');
  expect(current()).toHaveTextContent('Transition to Scale research and innovation call');
  expect(within(pane()).getByText('To check: the call may be open only to research institutions.')).toBeInTheDocument();
});

test('clicking a row selects it without leaving the feed', () => {
  const router = renderAt('/?fixture=reference');
  fireEvent.click(list().getByRole('link', { name: /Tenders for tyres/ }));
  expect(router.state.location.pathname).toBe('/o/horizon-tyres');
  expect(current()).toHaveTextContent('Tenders for tyres');
});

test('a stream chip filters the list', () => {
  renderAt('/?fixture=reference');
  fireEvent.click(screen.getByRole('button', { name: 'Funding' }));
  expect(screen.getByRole('button', { name: 'Funding' })).toHaveAttribute('aria-pressed', 'true');
  expect(rows().map((r) => r.querySelector('[role="img"]')!.getAttribute('aria-label'))).toEqual(['Funding', 'Funding']);
  expect(current()).toHaveTextContent('Transition to Scale');
});

test('an unknown id says so', () => {
  renderAt('/o/nope?fixture=reference');
  expect(screen.getByText(/could not find that item/)).toBeInTheDocument();
});

test.each([
  ['checking', 'Checking 8 sources', 6],
  ['source-down', 'We could not reach BNR today', 6],
  ['first-visit', 'Tell Blackkite what you do', 6],
])('?state=%s shows its card above the list', (state, title, count) => {
  renderAt(`/?fixture=reference&state=${state}`);
  expect(within(screen.getByRole('region', { name: 'Feed status' })).getByText(title)).toBeInTheDocument();
  expect(rows()).toHaveLength(count);
});

test('first visit: nothing is ranked', () => {
  renderAt('/?fixture=reference&state=first-visit');
  expect(list().queryByText(/fit ·/)).toBeNull();
  expect(list().getByText('World Food Programme')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Set up a profile' })).toBeInTheDocument();
});

test('source down links to the sources page', () => {
  renderAt('/?fixture=reference&state=source-down');
  expect(screen.getByRole('link', { name: 'See all sources' })).toHaveAttribute('href', '/sources?fixture=reference&state=source-down');
});

test('?state=nothing-new replaces the list and the pane', () => {
  renderAt('/?fixture=reference&state=nothing-new');
  expect(screen.getByText('Nothing new since yesterday')).toBeInTheDocument();
  expect(screen.queryByRole('region', { name: 'Opportunities' })).toBeNull();
  expect(screen.queryByRole('article')).toBeNull();
});

test('edge cases: long title, missing deadline, not scored, closed', () => {
  renderAt('/?fixture=edge-cases');
  expect(rows()).toHaveLength(4);
  expect(list().getByText(/Transition to Scale and Uptake/)).toBeInTheDocument();
  expect(list().getByText('No deadline stated')).toHaveClass('plain');
  expect(list().getByText('Not scored · develoPPP')).toBeInTheDocument();
  expect(list().getByText('Closed 23 Nov')).toHaveClass('plain');
  expect(rows().at(-1)).toHaveClass('closed');
  expect(rows()[0]).toHaveClass('new');
});

test.each(['javascript:alert(1)', 'data:text/html,hi', '/relative'])('an original notice URL of %s renders no link', (url) => {
  const item = reference.feed.items.find((i) => i.id === 'wfp-logistics')!;
  const was = item.detail.originalUrl;
  item.detail.originalUrl = url;
  try {
    renderAt('/?fixture=reference');
    expect(within(pane()).queryByRole('link', { name: 'Read the original' })).toBeNull();
  } finally {
    item.detail.originalUrl = was;
  }
});

test('an https original notice is linked, in a new tab without a referrer', () => {
  renderAt('/?fixture=reference');
  const a = within(pane()).getByRole('link', { name: 'Read the original' });
  expect(a).toHaveAttribute('href', 'https://www.jobinrwanda.com/jobs/tender');
  expect(a).toHaveAttribute('rel', 'noopener noreferrer');
});

test('a state card link navigates in the app, without a page load', () => {
  const router = renderAt('/?fixture=reference&state=source-down');
  const link = screen.getByRole('link', { name: 'See all sources' });
  // fireEvent returns false when the handler prevented the browser's own navigation.
  expect(fireEvent.click(link)).toBe(false);
  expect(router.state.location.pathname).toBe('/sources');
  expect(router.state.location.search).toBe('?fixture=reference&state=source-down');
});

test('a modified click on a state card link is left to the browser', () => {
  const router = renderAt('/?fixture=reference&state=source-down');
  expect(fireEvent.click(screen.getByRole('link', { name: 'See all sources' }), { ctrlKey: true })).toBe(true);
  expect(router.state.location.pathname).toBe('/');
});

test('saved look: pressed is the secondary button with the check icon before the same label; unpressed is primary with none', () => {
  renderAt('/?fixture=reference');
  const save = () => within(pane()).getByRole('button', { name: 'Save to shortlist' });
  // The reference screen (the visual board) never shows a saved item: primary, no icon.
  expect(save()).toHaveClass('primary');
  expect(save()).not.toHaveClass('secondary');
  expect(save().querySelector('svg')).toBeNull();
  fireEvent.click(save());
  expect(save()).toHaveAttribute('aria-pressed', 'true');
  expect(save()).toHaveClass('secondary');
  expect(save()).not.toHaveClass('primary');
  const icon = save().firstElementChild!;
  expect(icon.tagName.toLowerCase()).toBe('svg');
  expect(icon).toHaveAttribute('data-icon', 'check');
  expect(icon).toHaveAttribute('aria-hidden', 'true');
  expect(save()).toHaveTextContent(/^Save to shortlist$/);
  press('s');
  expect(save()).toHaveClass('primary');
  expect(save().querySelector('svg')).toBeNull();
});
