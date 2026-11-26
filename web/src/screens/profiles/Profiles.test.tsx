import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import type { Profile } from '../../api/types';
import { mockApi, status } from '../../test/mockApi';
import { COPY } from '../common/copy';
import { renderAt, setViewport } from '../feed/testUtils';
import { SIGN_IN } from '../SignIn';
import { EDITOR_COPY } from './ProfileEditor';
import { PROFILES_COPY } from './Profiles';
import { ERRORS } from './profileForm';

beforeEach(() => setViewport('desktop'));
afterEach(() => vi.unstubAllGlobals());

const ME = { id: 'u', email: 'c@x.rw', name: 'Clet', role: 'admin' };
const IRONJI: Profile = {
  id: 'p1',
  name: 'Ironji-Trade',
  type: 'business',
  version: 1,
  active: true,
  data: {
    streams: ['tender', 'funding', 'event'],
    services: ['dry freight', 'cold chain'],
    capacity: { model: 'partner network', trucksInNetwork: 1000, refrigeratedInNetwork: 100 },
    minContractRwf: 5000000,
  },
};
const AI: Profile = { id: 'p2', name: 'AI lab', type: 'business', version: 1, active: true, data: { streams: ['tender'], provisional: true } };
const PERSONAL: Profile = {
  id: 'p3',
  name: 'Personal',
  type: 'personal',
  version: 1,
  active: false,
  data: { streams: ['investment', 'event'], instruments: ['RSE shares'], eventTopics: [] },
};

const field = (label: string) => screen.getByLabelText(label);
const type = (label: string, value: string) => fireEvent.change(field(label), { target: { value } });

test('the list: each profile with its kind, streams and an edit link', async () => {
  mockApi({ 'GET /api/profiles': [IRONJI, AI, PERSONAL], 'GET /me': ME });
  renderAt('/profiles');
  const card = within(await screen.findByRole('region', { name: 'Your profiles' }));
  expect(card.getByText('Ironji-Trade')).toBeInTheDocument();
  expect(card.getByText('Business · Tenders, Funding, Events')).toBeInTheDocument();
  expect(card.getByText('Personal · Investments, Events')).toBeInTheDocument();
  expect(card.getByText(PROFILES_COPY.provisional)).toBeInTheDocument();
  expect(card.getByText(PROFILES_COPY.paused)).toBeInTheDocument();
  expect(card.getByRole('link', { name: 'Edit Ironji-Trade' })).toHaveAttribute('href', '/profiles/p1');
  expect(within(screen.getByRole('navigation', { name: 'Main' })).getByRole('link', { name: 'Profiles' })).toHaveAttribute('aria-current', 'page');
});

test('no profiles: the first-visit wording and the two ways to add one', async () => {
  mockApi({ 'GET /api/profiles': [], 'GET /me': ME });
  const router = renderAt('/profiles');
  expect(await screen.findByText(PROFILES_COPY.emptyTitle)).toBeInTheDocument();
  expect(
    screen.getByText('Add a profile for a business or for your own interests. Until then you see events and investments; tenders and funding need a profile to match against.'),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: PROFILES_COPY.addPersonal }));
  expect(router.state.location.pathname).toBe('/profiles/new/personal');
  expect(await screen.findByRole('heading', { level: 1, name: EDITOR_COPY.newPersonal })).toBeInTheDocument();
});

test('401 signs in', async () => {
  mockApi({ 'GET /api/profiles': status(401) });
  renderAt('/profiles');
  expect(await screen.findByRole('button', { name: SIGN_IN.button })).toBeInTheDocument();
});

test('edit: the form shows the profile, PATCH sends every field, and it says it re-ranks', async () => {
  const api = mockApi({ 'GET /api/profiles': [IRONJI], 'GET /me': ME, 'PATCH /api/profiles/p1': (body: unknown) => ({ ...IRONJI, ...(body as object), version: 2 }) });
  renderAt('/profiles/p1');
  expect(await screen.findByRole('heading', { level: 1, name: 'Ironji-Trade' })).toBeInTheDocument();
  expect(field(EDITOR_COPY.services)).toHaveValue('dry freight, cold chain');
  expect(field(EDITOR_COPY.trucks)).toHaveValue('1000');
  expect(field(EDITOR_COPY.minContract)).toHaveValue('5000000');
  expect(screen.getByRole('button', { name: 'Tenders' })).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getByRole('button', { name: 'Investments' })).toHaveAttribute('aria-pressed', 'false');

  type(EDITOR_COPY.services, 'dry freight, cold chain, warehousing');
  type(EDITOR_COPY.held, 'RDB company registration, RRA tax clearance');
  type(EDITOR_COPY.tonnageMin, '30');
  type(EDITOR_COPY.tonnageMax, '30');
  fireEvent.click(screen.getByRole('button', { name: 'Events' }));
  type(EDITOR_COPY.excludeKeywords, 'mining');
  fireEvent.click(screen.getByRole('button', { name: EDITOR_COPY.save }));

  expect(await screen.findByText(EDITOR_COPY.saved)).toBeInTheDocument();
  const patch = api.calls.find((c) => c.key === 'PATCH /api/profiles/p1')!.body as Profile;
  expect(patch).toMatchObject({
    name: 'Ironji-Trade',
    type: 'business',
    active: true,
    data: {
      streams: ['tender', 'funding'],
      services: ['dry freight', 'cold chain', 'warehousing'],
      registrationsHeld: ['RDB company registration', 'RRA tax clearance'],
      capacity: { model: 'partner network', trucksInNetwork: 1000, refrigeratedInNetwork: 100, tonnage: 30 },
      minContractRwf: 5000000,
      exclusions: { keywords: ['mining'] },
    },
  });
});

test('validation in the field-error style; nothing is sent until it is fixed', async () => {
  const api = mockApi({ 'GET /api/profiles': [IRONJI], 'GET /me': ME });
  renderAt('/profiles/p1');
  await screen.findByRole('heading', { level: 1, name: 'Ironji-Trade' });
  type(EDITOR_COPY.name, '');
  type(EDITOR_COPY.refrigerated, 'about a hundred');
  for (const s of ['Tenders', 'Funding', 'Events']) fireEvent.click(screen.getByRole('button', { name: s }));
  fireEvent.click(screen.getByRole('button', { name: EDITOR_COPY.save }));
  expect(field(EDITOR_COPY.name)).toHaveAccessibleDescription(ERRORS.name);
  expect(field(EDITOR_COPY.refrigerated)).toHaveAttribute('aria-invalid', 'true');
  expect(field(EDITOR_COPY.refrigerated)).toHaveAccessibleDescription(ERRORS.number);
  expect(screen.getByRole('group', { name: EDITOR_COPY.streams })).toHaveAccessibleDescription(ERRORS.streams);
  expect(screen.getByText(EDITOR_COPY.checkFields)).toBeInTheDocument();
  expect(api.calls.some((c) => c.key.startsWith('PATCH'))).toBe(false);
});

test('tonnage: a range of whole tonnes is sent as {min, max}, checked in the field-error style', async () => {
  const api = mockApi({ 'GET /api/profiles': [IRONJI], 'GET /me': ME, 'PATCH /api/profiles/p1': (b: unknown) => ({ ...IRONJI, ...(b as object) }) });
  renderAt('/profiles/p1');
  await screen.findByRole('heading', { level: 1, name: 'Ironji-Trade' });
  expect(field(EDITOR_COPY.tonnageMin)).toHaveAttribute('inputmode', 'decimal');
  type(EDITOR_COPY.tonnageMin, '20');
  type(EDITOR_COPY.tonnageMax, '5');
  fireEvent.click(screen.getByRole('button', { name: EDITOR_COPY.save }));
  expect(field(EDITOR_COPY.tonnageMax)).toHaveAccessibleDescription(ERRORS.tonnageOrder);
  expect(api.calls.some((c) => c.key.startsWith('PATCH'))).toBe(false);
  type(EDITOR_COPY.tonnageMax, '40');
  fireEvent.click(screen.getByRole('button', { name: EDITOR_COPY.save }));
  expect(await screen.findByText(EDITOR_COPY.saved)).toBeInTheDocument();
  const patch = api.calls.find((c) => c.key === 'PATCH /api/profiles/p1')!.body as Profile;
  expect(patch.data.capacity?.tonnage).toEqual({ min: 20, max: 40 });
});

test('a save that does not reach the server keeps the answers and says so', async () => {
  mockApi({ 'GET /api/profiles': [IRONJI], 'GET /me': ME, 'PATCH /api/profiles/p1': status(503) });
  renderAt('/profiles/p1');
  await screen.findByRole('heading', { level: 1, name: 'Ironji-Trade' });
  type(EDITOR_COPY.tonnageMin, '12');
  fireEvent.click(screen.getByRole('button', { name: EDITOR_COPY.save }));
  expect(await screen.findByText(new RegExp(COPY.unreachableTitle))).toBeInTheDocument();
  expect(field(EDITOR_COPY.tonnageMin)).toHaveValue('12');
});

test('the server refusing it (a name already used) gets its own plain message', async () => {
  mockApi({ 'GET /api/profiles': [IRONJI], 'GET /me': ME, 'PATCH /api/profiles/p1': status(422, { detail: 'name taken' }) });
  renderAt('/profiles/p1');
  await screen.findByRole('heading', { level: 1, name: 'Ironji-Trade' });
  fireEvent.click(screen.getByRole('button', { name: EDITOR_COPY.save }));
  expect(await screen.findByText(EDITOR_COPY.refused)).toBeInTheDocument();
});

test('new personal profile: chips for instruments and topics, POST, back to the list', async () => {
  const api = mockApi({ 'GET /api/profiles': [], 'GET /me': ME, 'POST /api/profiles': (b: unknown) => ({ id: 'p9', version: 1, ...(b as object) }) });
  const router = renderAt('/profiles/new/personal');
  await screen.findByRole('heading', { level: 1, name: EDITOR_COPY.newPersonal });
  expect(screen.queryByLabelText(EDITOR_COPY.services)).toBeNull();
  type(EDITOR_COPY.name, 'Personal');
  fireEvent.click(screen.getByRole('button', { name: 'treasury bonds and bills' }));
  fireEvent.click(screen.getByRole('button', { name: 'AI and tech' }));
  type(EDITOR_COPY.ticketMin, '100,000');
  fireEvent.click(screen.getByRole('button', { name: EDITOR_COPY.create }));
  await waitFor(() => expect(router.state.location.pathname).toBe('/profiles'));
  expect(api.calls.find((c) => c.key === 'POST /api/profiles')!.body).toMatchObject({
    name: 'Personal',
    type: 'personal',
    data: { streams: ['investment', 'event'], instruments: ['treasury bonds and bills'], eventTopics: ['AI and tech'], ticketRangeRwf: { min: 100000, max: null } },
  });
  expect(await screen.findByText(EDITOR_COPY.created)).toBeInTheDocument();
});

test('switches: provisional and active', async () => {
  const api = mockApi({ 'GET /api/profiles': [AI], 'GET /me': ME, 'PATCH /api/profiles/p2': AI });
  renderAt('/profiles/p2');
  await screen.findByRole('heading', { level: 1, name: 'AI lab' });
  const provisional = screen.getByRole('switch', { name: EDITOR_COPY.provisional });
  expect(provisional).toHaveAttribute('aria-checked', 'true');
  fireEvent.click(provisional);
  fireEvent.click(screen.getByRole('switch', { name: EDITOR_COPY.active }));
  fireEvent.click(screen.getByRole('button', { name: EDITOR_COPY.save }));
  await waitFor(() => expect(api.calls.some((c) => c.key === 'PATCH /api/profiles/p2')).toBe(true));
  expect(api.calls.find((c) => c.key === 'PATCH /api/profiles/p2')!.body).toMatchObject({ active: false, data: { provisional: false } });
});

test('delete asks first, then DELETE and back to the list', async () => {
  const api = mockApi({ 'GET /api/profiles': [IRONJI], 'GET /me': ME, 'DELETE /api/profiles/p1': undefined });
  const router = renderAt('/profiles/p1');
  await screen.findByRole('heading', { level: 1, name: 'Ironji-Trade' });
  fireEvent.click(screen.getByRole('button', { name: EDITOR_COPY.delete }));
  expect(screen.getByText(EDITOR_COPY.confirmDelete('Ironji-Trade'))).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: EDITOR_COPY.keep }));
  expect(api.calls.some((c) => c.key.startsWith('DELETE'))).toBe(false);
  fireEvent.click(screen.getByRole('button', { name: EDITOR_COPY.delete }));
  api.on('GET /api/profiles', []);
  fireEvent.click(screen.getByRole('button', { name: EDITOR_COPY.confirm }));
  await waitFor(() => expect(router.state.location.pathname).toBe('/profiles'));
  expect(api.calls.some((c) => c.key === 'DELETE /api/profiles/p1')).toBe(true);
  expect(await screen.findByText(EDITOR_COPY.deleted)).toBeInTheDocument();
});

test('an unknown profile id says so', async () => {
  mockApi({ 'GET /api/profiles': [IRONJI], 'GET /me': ME });
  renderAt('/profiles/nope');
  expect(await screen.findByText(EDITOR_COPY.notFound)).toBeInTheDocument();
});

test('phone: the editor sits in the phone frame, under More', async () => {
  setViewport('phone');
  mockApi({ 'GET /api/profiles': [IRONJI], 'GET /me': ME });
  renderAt('/profiles/p1');
  await screen.findByRole('heading', { level: 1, name: 'Ironji-Trade' });
  expect(within(screen.getByRole('navigation', { name: 'Main' })).getByRole('link', { name: 'More' })).toHaveAttribute('aria-current', 'page');
});

test('capacity: under "Capacity (transport and logistics)", open when it holds values', async () => {
  mockApi({ 'GET /api/profiles': [IRONJI], 'GET /me': ME });
  renderAt('/profiles/p1');
  await screen.findByRole('heading', { level: 1, name: 'Ironji-Trade' });
  const card = within(screen.getByRole('region', { name: 'Capacity (transport and logistics)' }));
  expect(card.getByText('Optional. Only needed if you move goods; leave it empty otherwise.')).toBeInTheDocument();
  expect(card.getByLabelText(EDITOR_COPY.trucks)).toHaveValue('1000');
  expect(card.queryByRole('button', { name: EDITOR_COPY.showCapacity })).toBeNull();
  expect(card.queryByRole('button', { name: EDITOR_COPY.hideCapacity })).toBeNull();
});

test('capacity: collapsed by default when empty; opens, and closes again while still empty', async () => {
  mockApi({ 'GET /api/profiles': [AI], 'GET /me': ME });
  renderAt('/profiles/p2');
  await screen.findByRole('heading', { level: 1, name: 'AI lab' });
  const region = screen.getByRole('region', { name: 'Capacity (transport and logistics)' });
  const card = within(region);
  expect(card.getByLabelText(EDITOR_COPY.trucks)).not.toBeVisible();
  const show = card.getByRole('button', { name: EDITOR_COPY.showCapacity });
  expect(show).toHaveAttribute('aria-expanded', 'false');
  expect(document.getElementById(show.getAttribute('aria-controls')!)).not.toBeVisible();
  fireEvent.click(show);
  expect(card.getByLabelText(EDITOR_COPY.trucks)).toBeVisible();
  // Focus moves to the first field, then back to the toggle when closed.
  expect(card.getByLabelText(EDITOR_COPY.capacityModel)).toHaveFocus();
  const hide = card.getByRole('button', { name: EDITOR_COPY.hideCapacity });
  expect(hide).toHaveAttribute('aria-expanded', 'true');
  fireEvent.click(hide);
  expect(card.getByLabelText(EDITOR_COPY.trucks)).not.toBeVisible();
  expect(card.getByRole('button', { name: EDITOR_COPY.showCapacity })).toHaveFocus();
  // Once something is typed it stays open.
  fireEvent.click(card.getByRole('button', { name: EDITOR_COPY.showCapacity }));
  type(EDITOR_COPY.trucks, '12');
  expect(card.queryByRole('button', { name: EDITOR_COPY.hideCapacity })).toBeNull();
  expect(card.getByLabelText(EDITOR_COPY.trucks)).toBeVisible();
});

test('capacity: a new business profile starts collapsed', async () => {
  mockApi({ 'GET /api/profiles': [], 'GET /me': ME });
  renderAt('/profiles/new/business');
  await screen.findByRole('heading', { level: 1, name: EDITOR_COPY.newBusiness });
  expect(screen.getByRole('button', { name: EDITOR_COPY.showCapacity })).toBeInTheDocument();
  expect(screen.getByLabelText(EDITOR_COPY.trucks)).not.toBeVisible();
});
