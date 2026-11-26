import { fireEvent, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import type { Profile } from '../../api/types';
import { mockApi } from '../../test/mockApi';
import { renderAt, setViewport } from '../feed/testUtils';
import { EDITOR_COPY } from './ProfileEditor';
import { ERRORS, toForm, toInput } from './profileForm';

/** Every profile field scoring reads is editable (M5, second user): organisation type, sectors, places; horizon, availability, budget. */

beforeEach(() => setViewport('desktop'));
afterEach(() => vi.unstubAllGlobals());

const ME = { id: 'u', email: 'n@x.rw', name: 'Nadia', role: 'member' };
const NGO: Profile = { id: 'p1', name: 'Health NGO', type: 'business', version: 1, active: true, data: { streams: ['funding'], services: ['community health'] } };
const PERSONAL: Profile = { id: 'p2', name: 'Savings', type: 'personal', version: 1, active: true, data: { streams: ['investment', 'event'] } };

const field = (label: string) => screen.getByLabelText(label);
const type = (label: string, value: string) => fireEvent.change(field(label), { target: { value } });

test('business: organisation type as one-choice chips with a hint, sectors and other places, all sent', async () => {
  const api = mockApi({ 'GET /me': ME, 'GET /api/profiles': [NGO], 'PATCH /api/profiles/p1': (b: unknown) => ({ ...NGO, ...(b as object) }) });
  renderAt('/profiles/p1');
  await screen.findByRole('heading', { level: 1, name: 'Health NGO' });
  const group = screen.getByRole('group', { name: EDITOR_COPY.organisationType });
  expect(group).toHaveAccessibleDescription(EDITOR_COPY.organisationTypeHint);
  const ngo = within(group).getByRole('button', { name: 'NGO or non-profit' });
  expect(ngo).toHaveAttribute('aria-pressed', 'false');
  fireEvent.click(ngo);
  expect(ngo).toHaveAttribute('aria-pressed', 'true');
  fireEvent.click(within(group).getByRole('button', { name: 'Company' }));
  expect(ngo).toHaveAttribute('aria-pressed', 'false');
  fireEvent.click(ngo);
  type(EDITOR_COPY.sectors, 'health, water and sanitation');
  expect(field(EDITOR_COPY.sectors)).toHaveAccessibleDescription(EDITOR_COPY.sectorsHint);
  type(EDITOR_COPY.locations, 'Musanze, Rubavu');
  fireEvent.click(screen.getByRole('button', { name: EDITOR_COPY.save }));
  expect(await screen.findByText(EDITOR_COPY.saved)).toBeInTheDocument();
  const patch = api.calls.find((c) => c.key === 'PATCH /api/profiles/p1')!.body as Profile;
  expect(patch.data).toMatchObject({ organisationType: 'ngo', sectors: ['health', 'water and sanitation'], locations: ['Musanze', 'Rubavu'] });
});

test('organisation type: not sent when never given; pressing the chosen chip again clears it to null', () => {
  const plain = toInput(toForm(NGO, 'business'), NGO.data).data;
  expect(plain).not.toHaveProperty('organisationType');
  const stored = { ...NGO.data, organisationType: 'cso' };
  const form = toForm({ ...NGO, data: stored }, 'business');
  expect(form.organisationType).toBe('cso');
  expect(toInput(form, stored).data.organisationType).toBe('cso');
  expect(toInput({ ...form, organisationType: '' }, stored).data.organisationType).toBeNull();
});

test('a stored organisation type outside the list shows as its own chip, chosen', async () => {
  mockApi({ 'GET /me': ME, 'GET /api/profiles': [{ ...NGO, data: { ...NGO.data, organisationType: 'cso' } }] });
  renderAt('/profiles/p1');
  const group = await screen.findByRole('group', { name: EDITOR_COPY.organisationType });
  expect(within(group).getByRole('button', { name: 'cso' })).toHaveAttribute('aria-pressed', 'true');
});

test('personal: horizon, availability and an event budget in francs, checked and sent', async () => {
  const api = mockApi({ 'GET /me': ME, 'GET /api/profiles': [PERSONAL], 'PATCH /api/profiles/p2': (b: unknown) => ({ ...PERSONAL, ...(b as object) }) });
  renderAt('/profiles/p2');
  await screen.findByRole('heading', { level: 1, name: 'Savings' });
  expect(screen.queryByRole('group', { name: EDITOR_COPY.organisationType })).toBeNull();
  type(EDITOR_COPY.horizon, '1 to 3 years');
  type(EDITOR_COPY.availability, 'weekends');
  type(EDITOR_COPY.budget, '50,000.5');
  fireEvent.click(screen.getByRole('button', { name: EDITOR_COPY.save }));
  expect(field(EDITOR_COPY.budget)).toHaveAccessibleDescription(ERRORS.rwf);
  expect(api.calls.some((c) => c.key.startsWith('PATCH'))).toBe(false);
  type(EDITOR_COPY.budget, '50,000');
  fireEvent.click(screen.getByRole('button', { name: EDITOR_COPY.save }));
  expect(await screen.findByText(EDITOR_COPY.saved)).toBeInTheDocument();
  const patch = api.calls.find((c) => c.key === 'PATCH /api/profiles/p2')!.body as Profile;
  expect(patch.data).toMatchObject({ horizon: '1 to 3 years', availability: 'weekends', budgetRwf: 50000 });
  expect(patch.data).not.toHaveProperty('organisationType');
});

test('empty answers are sent as null (not provided), never as empty text', () => {
  const d = toInput(toForm(PERSONAL, 'personal'), PERSONAL.data).data;
  expect(d).toMatchObject({ horizon: null, availability: null, budgetRwf: null, locations: null });
});
