import { act, fireEvent, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { setNowForTests } from '../../lib/now';
import { renderAt, setViewport } from './testUtils';

beforeEach(() => {
  setNowForTests('2026-11-24T14:00:00+02:00');
  setViewport('phone');
});
afterEach(() => {
  setNowForTests(null);
  vi.unstubAllGlobals();
});

test('the phone feed: header, greeting, five rows, chips with Events last, tab bar', () => {
  renderAt('/?fixture=reference');
  expect(screen.getByRole('img', { name: 'Blackkite' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Your account' })).toHaveTextContent('C');
  expect(screen.getByRole('heading', { level: 1, name: 'Good afternoon, Clet' })).toBeInTheDocument();
  expect(screen.getByText('Six things worth a look. One closes in 6 days.')).toBeInTheDocument();
  const chips = within(screen.getByRole('group', { name: 'Filter by stream' })).getAllByRole('button');
  expect(chips.map((c) => c.textContent)).toEqual(['All', 'Tenders', 'Investments', 'Funding', 'Events']);
  const rows = within(screen.getByRole('region', { name: 'Opportunities' })).getAllByRole('link');
  expect(rows).toHaveLength(5);
  expect(screen.queryByText('develoPPP Ventures, cohort 6')).toBeNull();
  expect(screen.getByText('Possible fit · NCST')).toBeInTheDocument();
  expect(screen.getByText('Kigali Convention Centre')).toBeInTheDocument();
  expect(screen.getByText('6 days left')).toHaveClass('small', 'solid');
  expect(rows[0]).toHaveAttribute('href', '/o/wfp-logistics?fixture=reference');
  const tabs = screen.getByRole('navigation', { name: 'Main' });
  expect(within(tabs).getAllByRole('link').map((l) => l.textContent)).toEqual(['Feed', 'Shortlist', 'Calendar', 'More']);
  expect(within(tabs).getByRole('link', { name: 'Feed' })).toHaveAttribute('aria-current', 'page');
  expect(screen.queryByRole('article')).toBeNull();
});

test('a row opens the opportunity', () => {
  const router = renderAt('/?fixture=reference');
  fireEvent.click(screen.getByRole('link', { name: /Tenders for tyres/ }));
  expect(router.state.location.pathname).toBe('/o/horizon-tyres');
  expect(screen.getByRole('heading', { level: 1, name: 'Tenders for tyres and vehicle spare parts' })).toBeInTheDocument();
});

test('state cards take the list position on the phone too', () => {
  renderAt('/?fixture=reference&state=checking');
  expect(within(screen.getByRole('region', { name: 'Feed status' })).getByRole('status')).toHaveTextContent('Checking 8 sources');
  expect(within(screen.getByRole('region', { name: 'Opportunities' })).getAllByRole('link')).toHaveLength(5);
});

const phoneRows = () => within(screen.getByRole('region', { name: 'Opportunities' })).getAllByRole('link');
const press = (key: string, init: KeyboardEventInit = {}) => act(() => void fireEvent.keyDown(window, { key, ...init }));

test('J and K move focus through the phone list, stopping at the ends', () => {
  renderAt('/?fixture=reference');
  press('j');
  expect(document.activeElement).toBe(phoneRows()[0]);
  press('j');
  press('j');
  expect(document.activeElement).toBe(phoneRows()[2]);
  press('k');
  expect(document.activeElement).toBe(phoneRows()[1]);
  for (let i = 0; i < 10; i++) press('j');
  expect(document.activeElement).toBe(phoneRows().at(-1));
  press('K');
  expect(document.activeElement).toBe(phoneRows().at(-2));
});

test('S saves the focused row; X removes it and focus moves to the next row', () => {
  renderAt('/?fixture=reference');
  press('j');
  press('s');
  expect(screen.getAllByRole('status').some((s) => s.textContent === 'Saved to shortlist: Logistics, transport and warehousing support')).toBe(true);
  press('x');
  expect(phoneRows()).toHaveLength(4);
  expect(screen.queryByText('Logistics, transport and warehousing support')).toBeNull();
  expect(document.activeElement).toBe(phoneRows()[0]);
  expect(phoneRows()[0]).toHaveTextContent('ABH Summit');
});

test('S and X do nothing when no row has focus', () => {
  renderAt('/?fixture=reference');
  press('s');
  press('x');
  expect(phoneRows()).toHaveLength(5);
});

test('keys are ignored with a modifier held or while typing (phone)', () => {
  renderAt('/?fixture=reference');
  press('j', { ctrlKey: true });
  press('j', { metaKey: true });
  press('j', { altKey: true });
  expect(document.activeElement).toBe(document.body);
  press('j');
  press('x', { shiftKey: true });
  const input = document.createElement('input');
  document.body.appendChild(input);
  act(() => void fireEvent.keyDown(input, { key: 'x' }));
  input.remove();
  expect(phoneRows()).toHaveLength(5);
});

test('dismissing the last phone row moves focus to the heading', () => {
  renderAt('/?fixture=reference');
  fireEvent.click(screen.getByRole('button', { name: 'Investments' }));
  expect(phoneRows()).toHaveLength(1);
  press('j');
  press('x');
  expect(screen.queryByRole('region', { name: 'Opportunities' })).toBeNull();
  expect(document.activeElement).toBe(screen.getByRole('heading', { level: 1 }));
});
