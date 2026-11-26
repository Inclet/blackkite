import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import type { OwnedDetail } from '../../api/m4';
import { setNowForTests } from '../../lib/now';
import { mockApi, status } from '../../test/mockApi';
import { OWN_COPY } from '../feed/OwnItem';
import { renderAt, setViewport } from '../feed/testUtils';
import { ITEM_ERRORS } from './itemForm';
import { ITEM_COPY } from './ItemEditor';

beforeEach(() => {
  setNowForTests('2026-11-24T14:00:00+02:00');
  setViewport('desktop');
});
afterEach(() => {
  setNowForTests(null);
  vi.unstubAllGlobals();
});

const ME = { id: 'u', email: 'c@x.rw', name: 'Clet', role: 'member' };
const TRUST = 'You added this item yourself, so nobody else has checked it.';

function owned(over: Partial<OwnedDetail['detail']['ownItem'] & object> = {}, title = 'Fuel supply'): OwnedDetail {
  return {
    id: 'own-1',
    stream: 'tender',
    title,
    organisation: 'Kigali Bus',
    fit: null,
    deadline: '2026-12-10',
    state: 'unseen',
    provisional: false,
    detail: {
      reasons: [],
      trust: { state: 'unconfirmed', desktop: TRUST, phone: TRUST },
      originalUrl: 'https://example.rw/n',
      sources: [],
      documents: [],
      changes: [],
      note: null,
      state: 'unseen',
      fields: [{ name: 'organisation', value: 'Kigali Bus' }],
      isManual: true,
      ownItem: { shareConsent: false, published: false, ...over },
    },
  };
}

function feedWith(items: unknown[]) {
  return { user: { name: 'Clet' }, sources: { checked: 1, when: 'today' }, digest: { channel: 'email' }, items };
}

test('add: errors in place, then creates and opens the item', async () => {
  const created = owned();
  const { detail: _d, ...row } = created;
  const api = mockApi({
    'GET /me': ME,
    'POST /api/items': created,
    'GET /api/opportunities/own-1': created,
    'GET /api/feed': feedWith([{ ...row, detail: { reasons: [], trust: created.detail.trust, originalUrl: created.detail.originalUrl } }]),
    'GET /api/shortlist': [],
    'GET /api/profiles': [{ id: 'p1' }],
  });
  const router = renderAt('/items/new');
  const form = within(screen.getByRole('form', { name: ITEM_COPY.addTitle }));
  fireEvent.click(form.getByRole('button', { name: ITEM_COPY.create }));
  expect(await form.findByText(ITEM_ERRORS.stream)).toBeInTheDocument();
  expect(form.getByText(ITEM_ERRORS.title)).toBeInTheDocument();
  expect(api.calls.some((c) => c.key === 'POST /api/items')).toBe(false);

  fireEvent.click(form.getByRole('button', { name: 'Tenders' }));
  fireEvent.change(form.getByLabelText(ITEM_COPY.title), { target: { value: 'Fuel supply' } });
  fireEvent.change(form.getByLabelText(ITEM_COPY.organisation), { target: { value: 'Kigali Bus' } });
  fireEvent.change(form.getByLabelText(ITEM_COPY.deadline), { target: { value: '10 Dec 2026, 5pm' } });
  fireEvent.change(form.getByLabelText(ITEM_COPY.value), { target: { value: '2,000,000' } });
  fireEvent.click(form.getByRole('button', { name: 'USD' }));
  fireEvent.change(form.getByLabelText(ITEM_COPY.url), { target: { value: 'ftp://x' } });
  fireEvent.click(form.getByRole('button', { name: ITEM_COPY.create }));
  expect(await form.findByText(ITEM_ERRORS.url)).toBeInTheDocument();
  fireEvent.change(form.getByLabelText(ITEM_COPY.url), { target: { value: 'https://example.rw/n' } });
  fireEvent.click(form.getByRole('button', { name: ITEM_COPY.create }));
  await waitFor(() => expect(router.state.location.pathname).toBe('/o/own-1'));
  expect(api.calls.find((c) => c.key === 'POST /api/items')!.body).toEqual({
    stream: 'tender',
    title: 'Fuel supply',
    organisation: 'Kigali Bus',
    deadline: '2026-12-10T17:00',
    eventStart: null,
    eventEnd: null,
    value: 2000000,
    currency: 'USD',
    location: null,
    url: 'https://example.rw/n',
    notes: null,
  });
  expect(await screen.findByText(OWN_COPY.private)).toBeInTheDocument();
});

test('events ask for start and end dates instead of a deadline', () => {
  mockApi({ 'GET /me': ME });
  renderAt('/items/new');
  fireEvent.click(screen.getByRole('button', { name: 'Events' }));
  // Typed text, not a native date picker; the hint gives the format.
  expect(screen.getByLabelText(ITEM_COPY.eventStart)).toHaveAttribute('type', 'text');
  expect(screen.getByLabelText(ITEM_COPY.eventStart)).toHaveAccessibleDescription(ITEM_COPY.dateHint);
  expect(screen.getByLabelText(ITEM_COPY.eventEnd)).toBeInTheDocument();
  expect(screen.queryByLabelText(ITEM_COPY.deadline)).toBeNull();
});

test('a date without its year is caught before sending, with the format in the hint', async () => {
  const api = mockApi({ 'GET /me': ME });
  renderAt('/items/new');
  fireEvent.click(screen.getByRole('button', { name: 'Tenders' }));
  fireEvent.change(screen.getByLabelText(ITEM_COPY.title), { target: { value: 'Fuel supply' } });
  const deadline = screen.getByLabelText(ITEM_COPY.deadline);
  expect(ITEM_COPY.dateHint).toBe('With the year, such as 7 Dec 2026 or 7 Dec 2026, 5pm.');
  fireEvent.change(deadline, { target: { value: '10 Dec' } });
  fireEvent.click(screen.getByRole('button', { name: ITEM_COPY.create }));
  expect(await screen.findByText(ITEM_ERRORS.date)).toBeInTheDocument();
  expect(deadline).toHaveAttribute('aria-invalid', 'true');
  expect(api.calls.some((c) => c.key.startsWith('POST'))).toBe(false);
});

test('a refused or unreachable save says so and keeps the form', async () => {
  const api = mockApi({ 'GET /me': ME, 'POST /api/items': status(422, { detail: 'x' }) });
  renderAt('/items/new');
  fireEvent.click(screen.getByRole('button', { name: 'Funding' }));
  fireEvent.change(screen.getByLabelText(ITEM_COPY.title), { target: { value: 'Grant' } });
  fireEvent.click(screen.getByRole('button', { name: ITEM_COPY.create }));
  expect(await screen.findByText(ITEM_COPY.refused)).toBeInTheDocument();
  api.on('POST /api/items', status(503));
  fireEvent.click(screen.getByRole('button', { name: ITEM_COPY.create }));
  expect(await screen.findByText(ITEM_COPY.unreachable)).toBeInTheDocument();
  expect(screen.getByLabelText(ITEM_COPY.title)).toHaveValue('Grant');
});

test('edit: prefilled from what the owner entered, PATCH, back to the item', async () => {
  const api = mockApi({ 'GET /me': ME, 'GET /api/opportunities/own-1': owned(), 'PATCH /api/items/own-1': owned({}, 'Fuel supply, phase 2') });
  const router = renderAt('/items/own-1/edit');
  const title = await screen.findByLabelText(ITEM_COPY.title);
  expect(title).toHaveValue('Fuel supply');
  expect(screen.getByRole('button', { name: 'Tenders' })).toHaveAttribute('aria-pressed', 'true');
  fireEvent.change(title, { target: { value: 'Fuel supply, phase 2' } });
  fireEvent.change(screen.getByLabelText(ITEM_COPY.organisation), { target: { value: '' } });
  fireEvent.click(screen.getByRole('button', { name: ITEM_COPY.save }));
  await waitFor(() => expect(router.state.location.pathname).toBe('/o/own-1'));
  const body = api.calls.find((c) => c.key === 'PATCH /api/items/own-1')!.body as Record<string, unknown>;
  expect(body).toEqual({ title: 'Fuel supply, phase 2', organisation: null });
});

test('edit: an untouched save of a same-day timed event sends no changes and keeps the end time', async () => {
  const item = owned();
  Object.assign(item, { stream: 'event', deadline: null, eventDates: { start: '2026-12-07', end: '2026-12-07' } });
  item.detail.fields = [
    { name: 'eventStart', value: '2026-12-07T09:00:00+02:00' },
    { name: 'eventEnd', value: '2026-12-07T13:30:00+02:00' },
  ];
  const api = mockApi({ 'GET /me': ME, 'GET /api/opportunities/own-1': item, 'PATCH /api/items/own-1': item });
  const router = renderAt('/items/own-1/edit');
  expect(await screen.findByLabelText(ITEM_COPY.eventEnd)).toHaveValue('7 Dec 2026, 1:30pm');
  expect(screen.getByLabelText(ITEM_COPY.eventStart)).toHaveValue('7 Dec 2026, 9am');
  fireEvent.click(screen.getByRole('button', { name: ITEM_COPY.save }));
  await waitFor(() => expect(router.state.location.pathname).toBe('/o/own-1'));
  expect(api.calls.find((c) => c.key === 'PATCH /api/items/own-1')!.body).toEqual({});
});

test('edit someone else\'s item: a plain refusal', async () => {
  const other = owned();
  delete other.detail.ownItem;
  mockApi({ 'GET /me': ME, 'GET /api/opportunities/own-1': other });
  renderAt('/items/own-1/edit');
  expect(await screen.findByText(ITEM_COPY.notOwner)).toBeInTheDocument();
});

function ownFeed(item: OwnedDetail, extra: Record<string, unknown> = {}) {
  const { detail, ...row } = item;
  return mockApi({
    'GET /me': ME,
    'GET /api/feed': feedWith([{ ...row, detail: { reasons: [], trust: detail.trust, originalUrl: detail.originalUrl } }]),
    'GET /api/shortlist': [],
    'GET /api/profiles': [{ id: 'p1' }],
    'GET /api/opportunities/own-1': item,
    ...extra,
  });
}

test('on the item: private Tag, consent switch with rollback, delete with a confirm', async () => {
  const api = ownFeed(owned(), { 'PUT /api/items/own-1/share-consent': status(503), 'DELETE /api/items/own-1': undefined });
  const router = renderAt('/o/own-1');
  expect(await screen.findByText(OWN_COPY.private)).toBeInTheDocument();
  const share = screen.getByRole('switch', { name: OWN_COPY.share });
  expect(share).toHaveAttribute('aria-checked', 'false');
  fireEvent.click(share);
  expect(await screen.findByText(OWN_COPY.shareFailed)).toBeInTheDocument();
  expect(share).toHaveAttribute('aria-checked', 'false');
  api.on('PUT /api/items/own-1/share-consent', { allow: true });
  fireEvent.click(share);
  expect(await screen.findByText(OWN_COPY.shareOn)).toBeInTheDocument();
  expect(share).toHaveAttribute('aria-checked', 'true');
  expect(api.calls.filter((c) => c.key === 'PUT /api/items/own-1/share-consent').at(-1)!.body).toEqual({ allow: true });

  fireEvent.click(screen.getByRole('button', { name: `${OWN_COPY.edit}: Fuel supply` }));
  expect(router.state.location.pathname).toBe('/items/own-1/edit');
  await act(() => router.navigate('/o/own-1'));
  const del = await screen.findByRole('button', { name: `${OWN_COPY.delete}: Fuel supply` });
  fireEvent.click(del);
  fireEvent.click(screen.getByRole('button', { name: OWN_COPY.confirmNo }));
  expect(del).toHaveFocus();
  expect(api.calls.some((c) => c.key === 'DELETE /api/items/own-1')).toBe(false);
  fireEvent.click(del);
  fireEvent.click(screen.getByRole('button', { name: OWN_COPY.confirmYes }));
  await waitFor(() => expect(router.state.location.pathname).toBe('/'));
  expect(screen.getByText(OWN_COPY.deleted('Fuel supply'))).toBeInTheDocument();
  expect(screen.queryByRole('link', { name: /Fuel supply/ })).toBeNull();
});

test('published: the switch is locked on, with the reason', async () => {
  ownFeed(owned({ published: true, shareConsent: true }));
  renderAt('/o/own-1');
  expect(await screen.findByText(OWN_COPY.public)).toBeInTheDocument();
  const share = screen.getByRole('switch', { name: OWN_COPY.share });
  expect(share).toBeDisabled();
  expect(share).toHaveAttribute('aria-checked', 'true');
  expect(screen.getByText(OWN_COPY.shared)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /^Edit:/ })).toBeNull();
  expect(screen.queryByRole('button', { name: /^Delete:/ })).toBeNull();
});

test('withdrawing consent after an admin published it: 409 locks the switch with the reason', async () => {
  ownFeed(owned({ shareConsent: true }), { 'PUT /api/items/own-1/share-consent': status(409, { detail: 'public now' }) });
  renderAt('/o/own-1');
  const share = await screen.findByRole('switch', { name: OWN_COPY.share });
  fireEvent.click(share);
  await waitFor(() => expect(share).toBeDisabled());
  expect(share).toHaveAttribute('aria-checked', 'true');
  expect(screen.getAllByText(OWN_COPY.shared).length).toBeGreaterThan(0);
});

test('edit a published item: a plain refusal instead of the form', async () => {
  mockApi({ 'GET /me': ME, 'GET /api/opportunities/own-1': owned({ published: true, shareConsent: true }) });
  renderAt('/items/own-1/edit');
  expect(await screen.findByText(ITEM_COPY.published)).toBeInTheDocument();
  expect(screen.queryByLabelText(ITEM_COPY.title)).toBeNull();
});

test('the API\'s refused fields show next to their fields', async () => {
  mockApi({
    'GET /me': ME,
    'POST /api/items': status(422, { detail: 'Deadline: include the year, for example 30 Nov 2026.', errors: [{ field: 'deadline', message: 'include the year, for example 30 Nov 2026' }] }),
  });
  renderAt('/items/new');
  fireEvent.click(screen.getByRole('button', { name: 'Tenders' }));
  fireEvent.change(screen.getByLabelText(ITEM_COPY.title), { target: { value: 'X' } });
  fireEvent.change(screen.getByLabelText(ITEM_COPY.deadline), { target: { value: '2026-12-10' } });
  fireEvent.click(screen.getByRole('button', { name: ITEM_COPY.create }));
  expect(await screen.findByText('Include the year, for example 30 Nov 2026.')).toBeInTheDocument();
  expect(screen.getByLabelText(ITEM_COPY.deadline)).toHaveAttribute('aria-invalid', 'true');
});

test('other people\'s items show no owner controls', async () => {
  const item = owned();
  delete item.detail.ownItem;
  ownFeed(item);
  renderAt('/o/own-1');
  await screen.findByText('Your progress');
  expect(screen.queryByText(OWN_COPY.private)).toBeNull();
  expect(screen.queryByRole('switch', { name: OWN_COPY.share })).toBeNull();
});

test('"Add an item" is on the live feed and the shortlist, never on fixtures', async () => {
  ownFeed(owned());
  const router = renderAt('/');
  fireEvent.click(await screen.findByRole('button', { name: ITEM_COPY.add }));
  expect(router.state.location.pathname).toBe('/items/new');
});

test('no "Add an item" on fixtures', () => {
  mockApi({});
  renderAt('/?fixture=reference');
  expect(screen.queryByRole('button', { name: ITEM_COPY.add })).toBeNull();
});
