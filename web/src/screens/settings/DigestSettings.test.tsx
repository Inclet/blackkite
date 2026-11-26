import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import type { DigestSettings } from '../../api/types';
import { mockApi, status } from '../../test/mockApi';
import { COPY } from '../common/copy';
import { renderAt, setViewport } from '../feed/testUtils';
import { SIGN_IN } from '../SignIn';
import { DIGEST_COPY } from './DigestSettings';

beforeEach(() => setViewport('desktop'));
afterEach(() => vi.unstubAllGlobals());

const ME = { id: 'u', email: 'c@x.rw', name: 'Clet', role: 'admin' };
const SETTINGS: DigestSettings = { channel: 'email', frequency: 'weekly', day: 'mon', alertMinFit: 'strong', streams: null };

const sw = (name: string) => screen.getByRole('switch', { name });
const chip = (name: string) => screen.getByRole('button', { name });
const put = (api: ReturnType<typeof mockApi>) => api.calls.filter((c) => c.key === 'PUT /api/digest-settings').at(-1)?.body;

test('shows the settings: weekly on Monday, the board\'s Urgent alerts switch, the threshold and streams', async () => {
  mockApi({ 'GET /api/digest-settings': SETTINGS, 'GET /me': ME });
  renderAt('/settings/digest');
  expect(await screen.findByText('Every Monday, by email to c@x.rw.')).toBeInTheDocument();
  expect(sw(DIGEST_COPY.weekly)).toHaveAttribute('aria-checked', 'true');
  expect(sw('Urgent alerts')).toHaveAttribute('aria-checked', 'true');
  expect(sw('Urgent alerts')).toHaveAccessibleDescription('Email me the day a strong fit closes within 5 days.');
  // The fit words, never the internal score.
  expect(screen.getByRole('group', { name: DIGEST_COPY.threshold })).toBeInTheDocument();
  expect(chip(DIGEST_COPY.strongOnly)).toHaveAttribute('aria-pressed', 'true');
  expect(chip(DIGEST_COPY.strongAndGood)).toHaveAttribute('aria-pressed', 'false');
  expect(within(screen.getByRole('form', { name: 'Digest settings' })).queryByText(/\d{2}/)).toBeNull();
  expect(screen.queryByRole('textbox')).toBeNull();
  expect(chip(DIGEST_COPY.profileStreams)).toHaveAttribute('aria-pressed', 'true');
  expect(chip('Tenders')).toHaveAttribute('aria-pressed', 'false');
});

test('round trip: off, strong and good fits, two streams; PUT sends the whole setting', async () => {
  const api = mockApi({ 'GET /api/digest-settings': SETTINGS, 'GET /me': ME, 'PUT /api/digest-settings': (b: unknown) => b });
  renderAt('/settings/digest');
  await screen.findByText('Every Monday, by email to c@x.rw.');
  fireEvent.click(sw(DIGEST_COPY.weekly));
  fireEvent.click(chip(DIGEST_COPY.strongAndGood));
  expect(chip(DIGEST_COPY.strongOnly)).toHaveAttribute('aria-pressed', 'false');
  // The description follows the choice.
  expect(sw('Urgent alerts')).toHaveAccessibleDescription('Email me the day a strong or good fit closes within 5 days.');
  fireEvent.click(chip(DIGEST_COPY.strongOnly));
  expect(sw('Urgent alerts')).toHaveAccessibleDescription('Email me the day a strong fit closes within 5 days.');
  fireEvent.click(chip(DIGEST_COPY.strongAndGood));
  fireEvent.click(chip('Events'));
  fireEvent.click(chip('Tenders'));
  expect(chip(DIGEST_COPY.profileStreams)).toHaveAttribute('aria-pressed', 'false');
  fireEvent.click(chip(DIGEST_COPY.save));
  expect(await screen.findByText(DIGEST_COPY.saved)).toBeInTheDocument();
  expect(put(api)).toEqual({ channel: 'email', frequency: 'off', day: 'mon', alertMinFit: 'good', streams: ['tender', 'event'] });
});

test('alerts off sends a null alertMinFit and hides the choice; back on starts at strong fits only', async () => {
  const api = mockApi({ 'GET /api/digest-settings': { ...SETTINGS, alertMinFit: null, streams: ['tender'] }, 'GET /me': ME, 'PUT /api/digest-settings': (b: unknown) => b });
  renderAt('/settings/digest');
  await screen.findByText(/Every Monday/);
  expect(sw('Urgent alerts')).toHaveAttribute('aria-checked', 'false');
  expect(screen.queryByRole('group', { name: DIGEST_COPY.threshold })).toBeNull();
  fireEvent.click(sw('Urgent alerts'));
  expect(chip(DIGEST_COPY.strongOnly)).toHaveAttribute('aria-pressed', 'true');
  fireEvent.click(sw('Urgent alerts'));
  // Removing the last stream means "my profiles' streams" again.
  fireEvent.click(chip('Tenders'));
  expect(chip(DIGEST_COPY.profileStreams)).toHaveAttribute('aria-pressed', 'true');
  fireEvent.click(chip(DIGEST_COPY.save));
  await waitFor(() => expect(put(api)).toMatchObject({ alertMinFit: null, streams: null, frequency: 'weekly' }));
});

test('switching alerts on sends "strong"', async () => {
  const api = mockApi({ 'GET /api/digest-settings': { ...SETTINGS, alertMinFit: null }, 'GET /me': ME, 'PUT /api/digest-settings': (b: unknown) => b });
  renderAt('/settings/digest');
  await screen.findByText(/Every Monday/);
  fireEvent.click(sw('Urgent alerts'));
  fireEvent.click(chip(DIGEST_COPY.save));
  await waitFor(() => expect(put(api)).toMatchObject({ alertMinFit: 'strong' }));
});

test('a stored "good" reads as strong and good fits, and is sent back as stored', async () => {
  const api = mockApi({ 'GET /api/digest-settings': { ...SETTINGS, alertMinFit: 'good' }, 'GET /me': ME, 'PUT /api/digest-settings': (b: unknown) => b });
  renderAt('/settings/digest');
  await screen.findByText(/Every Monday/);
  expect(chip(DIGEST_COPY.strongAndGood)).toHaveAttribute('aria-pressed', 'true');
  fireEvent.click(chip(DIGEST_COPY.save));
  await waitFor(() => expect(put(api)).toMatchObject({ alertMinFit: 'good' }));
  fireEvent.click(chip(DIGEST_COPY.strongOnly));
  fireEvent.click(chip(DIGEST_COPY.save));
  await waitFor(() => expect(put(api)).toMatchObject({ alertMinFit: 'strong' }));
});

test.each([
  ['unreachable', status(500), new RegExp(COPY.unreachableTitle)],
  ['refused', status(422), new RegExp(DIGEST_COPY.refused)],
])('a save that fails (%s) says so and keeps the answers', async (_n, response, text) => {
  mockApi({ 'GET /api/digest-settings': SETTINGS, 'GET /me': ME, 'PUT /api/digest-settings': response });
  renderAt('/settings/digest');
  await screen.findByText(/Every Monday/);
  fireEvent.click(sw(DIGEST_COPY.weekly));
  fireEvent.click(chip(DIGEST_COPY.save));
  expect(await screen.findByText(text)).toBeInTheDocument();
  expect(sw(DIGEST_COPY.weekly)).toHaveAttribute('aria-checked', 'false');
});

test('401 signs in; unreachable on load offers Try again', async () => {
  mockApi({ 'GET /api/digest-settings': status(401) });
  renderAt('/settings/digest');
  expect(await screen.findByRole('button', { name: SIGN_IN.button })).toBeInTheDocument();
});

test('unreachable on load offers Try again', async () => {
  const api = mockApi({ 'GET /api/digest-settings': status(502), 'GET /me': ME });
  renderAt('/settings/digest');
  expect(await screen.findByText(COPY.unreachableTitle)).toBeInTheDocument();
  api.on('GET /api/digest-settings', SETTINGS);
  fireEvent.click(chip(COPY.tryAgain));
  expect(await screen.findByText(/Every Monday/)).toBeInTheDocument();
});

test('the address shown is the account email from GET /me; PUT sends only the keys the API takes', async () => {
  const api = mockApi({
    'GET /api/digest-settings': { ...SETTINGS, address: 'old@x.rw' },
    'GET /me': { ...ME, email: 'clet@ironji.rw' },
    'PUT /api/digest-settings': (b: unknown) => b,
  });
  renderAt('/settings/digest');
  expect(await screen.findByText('Every Monday, by email to clet@ironji.rw.')).toBeInTheDocument();
  fireEvent.click(chip(DIGEST_COPY.save));
  expect(await screen.findByText(DIGEST_COPY.saved)).toBeInTheDocument();
  expect(Object.keys(put(api) as object).sort()).toEqual(['alertMinFit', 'channel', 'day', 'frequency', 'streams']);
});
