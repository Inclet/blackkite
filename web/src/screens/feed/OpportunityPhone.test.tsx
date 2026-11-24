import { fireEvent, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { reference } from '../../fixtures/reference';
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

test('the opportunity page reads as the board', () => {
  renderAt('/o/wfp-logistics?fixture=reference');
  expect(screen.getByRole('link', { name: 'Feed' })).toHaveAttribute('href', '/?fixture=reference');
  expect(screen.getByText('Tender')).toBeInTheDocument();
  expect(screen.getByText('Ironji-Trade')).toBeInTheDocument();
  expect(screen.getByText('6 days left')).toHaveClass('solid');
  expect(screen.getByRole('heading', { level: 1, name: 'Logistics, transport and warehousing support' })).toBeInTheDocument();
  expect(screen.getByText('Strong fit · why this matched')).toBeInTheDocument();
  expect(screen.getByText(/^To check: WFP's transport call in May/)).toHaveClass('note');
  expect(screen.getByText("Found on Job in Rwanda, posted 9 Nov. Check the date on WFP's own site before you act.").parentElement).toHaveClass('stone');
  expect(screen.getByRole('link', { name: 'Read the original notice' })).toHaveClass('block');
  const actions = within(screen.getByRole('group', { name: 'Actions' }));
  expect(actions.getByRole('button', { name: 'Save to shortlist' })).toHaveClass('large', 'primary');
  expect(actions.getByRole('button', { name: 'Not for me' })).toHaveClass('large', 'secondary');
});

test('save toggles; not for me returns to a feed without the item', () => {
  const router = renderAt('/o/wfp-logistics?fixture=reference');
  fireEvent.click(screen.getByRole('button', { name: 'Save to shortlist' }));
  expect(screen.getByRole('button', { name: 'Save to shortlist' })).toHaveAttribute('aria-pressed', 'true');
  fireEvent.click(screen.getByRole('button', { name: 'Save to shortlist' }));
  expect(screen.getByRole('button', { name: 'Save to shortlist' })).toHaveAttribute('aria-pressed', 'false');
  fireEvent.click(screen.getByRole('button', { name: 'Save to shortlist' }));
  fireEvent.click(screen.getByRole('button', { name: 'Not for me' }));
  expect(router.state.location.pathname).toBe('/');
  expect(screen.queryByText('Logistics, transport and warehousing support')).toBeNull();
  expect(within(screen.getByRole('region', { name: 'Opportunities' })).getAllByRole('link')).toHaveLength(4);
  // Focus lands on the row that followed the dismissed one.
  expect(document.activeElement).toHaveTextContent('ABH Summit');
});

test('an unknown id says so and links back', () => {
  renderAt('/o/nope?fixture=reference');
  expect(screen.getByRole('heading', { level: 1, name: 'We could not find that item' })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Feed' })).toBeInTheDocument();
});

test('a non-http original notice URL renders no link on the phone', () => {
  const item = reference.feed.items.find((i) => i.id === 'wfp-logistics')!;
  const was = item.detail.originalUrl;
  item.detail.originalUrl = 'javascript:alert(1)';
  try {
    renderAt('/o/wfp-logistics?fixture=reference');
    expect(screen.queryByRole('link', { name: 'Read the original notice' })).toBeNull();
  } finally {
    item.detail.originalUrl = was;
  }
});
