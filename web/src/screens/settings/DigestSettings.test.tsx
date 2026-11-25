import { fireEvent, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import type { DigestSettings } from '../../api/types';
import { mockApi, status } from '../../test/mockApi';
import { COPY } from '../common/copy';
import { renderAt, setViewport } from '../feed/testUtils';
import { SIGN_IN } from '../SignIn';
import { ALERT_THRESHOLDS, choiceFor, DIGEST_COPY } from './DigestSettings';

beforeEach(() => setViewport('desktop'));
afterEach(() => vi.unstubAllGlobals());

const ME = { id: 'u', email: 'c@x.rw', name: 'Clet', role: 'admin' };
const SETTINGS: DigestSettings = { channel: 'email', address: 'c@x.rw', frequency: 'weekly', day: 'mon', alertThreshold: 75, streams: null };

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
  expect(screen.queryByText(/75/)).toBeNull();
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
  fireEvent.click(chip('Events'));
  fireEvent.click(chip('Tenders'));
  expect(chip(DIGEST_COPY.profileStreams)).toHaveAttribute('aria-pressed', 'false');
  fireEvent.click(chip(DIGEST_COPY.save));
  expect(await screen.findByText(DIGEST_COPY.saved)).toBeInTheDocument();
  expect(put(api)).toEqual({ channel: 'email', address: 'c@x.rw', frequency: 'off', day: 'mon', alertThreshold: ALERT_THRESHOLDS.good, streams: ['tender', 'event'] });
});

test('alerts off sends a null threshold and hides the choice; back on starts at strong fits only', async () => {
  const api = mockApi({ 'GET /api/digest-settings': { ...SETTINGS, alertThreshold: null, streams: ['tender'] }, 'GET /me': ME, 'PUT /api/digest-settings': (b: unknown) => b });
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
  await waitFor(() => expect(put(api)).toMatchObject({ alertThreshold: null, streams: null, frequency: 'weekly' }));
});

test('switching alerts on sends the strong value', async () => {
  const api = mockApi({ 'GET /api/digest-settings': { ...SETTINGS, alertThreshold: null }, 'GET /me': ME, 'PUT /api/digest-settings': (b: unknown) => b });
  renderAt('/settings/digest');
  await screen.findByText(/Every Monday/);
  fireEvent.click(sw('Urgent alerts'));
  fireEvent.click(chip(DIGEST_COPY.save));
  await waitFor(() => expect(put(api)).toMatchObject({ alertThreshold: ALERT_THRESHOLDS.strong }));
});

test('a stored value set some other way is kept until the choice changes', async () => {
  const api = mockApi({ 'GET /api/digest-settings': { ...SETTINGS, alertThreshold: 70 }, 'GET /me': ME, 'PUT /api/digest-settings': (b: unknown) => b });
  renderAt('/settings/digest');
  await screen.findByText(/Every Monday/);
  expect(chip(DIGEST_COPY.strongAndGood)).toHaveAttribute('aria-pressed', 'true');
  fireEvent.click(chip(DIGEST_COPY.save));
  await waitFor(() => expect(put(api)).toMatchObject({ alertThreshold: 70 }));
  fireEvent.click(chip(DIGEST_COPY.strongOnly));
  fireEvent.click(chip(DIGEST_COPY.save));
  await waitFor(() => expect(put(api)).toMatchObject({ alertThreshold: ALERT_THRESHOLDS.strong }));
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

test('choiceFor: at or above the strong value is strong only; null starts at strong', () => {
  expect(choiceFor(ALERT_THRESHOLDS.strong)).toBe('strong');
  expect(choiceFor(100)).toBe('strong');
  expect(choiceFor(ALERT_THRESHOLDS.strong - 1)).toBe('good');
  expect(choiceFor(ALERT_THRESHOLDS.good)).toBe('good');
  expect(choiceFor(0)).toBe('good');
  expect(choiceFor(null)).toBe('strong');
});
