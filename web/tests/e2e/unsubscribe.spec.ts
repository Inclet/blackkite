import { expect, test } from '@playwright/test';
import { anonymousSeen, open, stubSession } from './helpers';
import { STUB_COOKIE, UNSUBSCRIBE_INVALID } from './stubApi';

const SETTINGS = 'Change your email settings';

/** The session's digest settings, read straight from the stub API. */
async function digestOf(sid: string): Promise<Record<string, unknown>> {
  const res = await fetch(`http://127.0.0.1:${process.env.BK_E2E_API_PORT}/api/digest-settings`, {
    headers: { Cookie: `${STUB_COOKIE}=${sid}` },
  });
  return (await res.json()) as Record<string, unknown>;
}

test('a digest link: nothing on load, the token leaves the URL, the button posts it through the proxy', async ({ page }, testInfo) => {
  const api = await stubSession(page, testInfo.testId);
  const sid = testInfo.testId.replace(/[^\w-]/g, '_');
  await page.setViewportSize({ width: 390, height: 844 });
  await open(page, '/unsubscribe#token=digest-abc');
  await expect(page.getByRole('heading', { level: 1, name: 'Emails from Blackkite' })).toBeVisible();
  await expect.poll(() => page.url()).toMatch(/\/unsubscribe$/);
  expect(page.url()).not.toContain('digest-abc');
  await expect(page.locator('meta[name="referrer"]')).toHaveAttribute('content', 'no-referrer');
  // The page is a web route, and opening it changes nothing (link scanners open URLs).
  expect(await api.seen()).toEqual([]);
  expect((await digestOf(sid)).frequency).toBe('weekly');

  await page.getByRole('button', { name: 'Stop these emails' }).click();
  await expect(page.getByText("You won't get these emails any more.")).toBeVisible();
  await expect(page.getByRole('button')).toHaveCount(0);

  const seen = (await api.seen()).filter((r) => r.url.startsWith('/api/unsubscribe'));
  expect(seen).toHaveLength(1);
  expect(seen[0]!.method).toBe('POST');
  expect(seen[0]!.url).toBe('/api/unsubscribe');
  expect(seen[0]!.contentType).toContain('application/json');
  expect(JSON.parse(seen[0]!.body)).toEqual({ token: 'digest-abc' });
  expect((await digestOf(sid)).frequency).toBe('off');

  await page.getByRole('link', { name: SETTINGS }).click();
  await expect.poll(() => new URL(page.url()).pathname).toBe('/settings/digest');
});

test('no session needed: an alert link works signed out', async ({ page }) => {
  const token = `alert-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  await page.setViewportSize({ width: 1440, height: 900 });
  await open(page, `/unsubscribe#token=${token}`);
  await page.getByRole('button', { name: 'Stop these emails' }).click();
  await expect(page.getByText("You won't get these alerts any more.")).toBeVisible();
  const mine = (await anonymousSeen()).filter((r) => r.url === '/api/unsubscribe' && r.body.includes(token));
  expect(mine).toHaveLength(1);
  expect(JSON.parse(mine[0]!.body)).toEqual({ token });
});

test('a bad link: the API’s words and the settings link', async ({ page }, testInfo) => {
  await stubSession(page, testInfo.testId);
  await open(page, '/unsubscribe#token=revoked');
  await page.getByRole('button', { name: 'Stop these emails' }).click();
  await expect(page.getByText(UNSUBSCRIBE_INVALID)).toBeVisible();
  await expect(page.getByRole('link', { name: SETTINGS })).toHaveAttribute('href', '/settings/digest');
  await expect(page.getByRole('button')).toHaveCount(0);
});

test('rate-limited: too many tries, and the button stays', async ({ page }, testInfo) => {
  await stubSession(page, testInfo.testId);
  await open(page, '/unsubscribe#token=busy');
  await page.getByRole('button', { name: 'Stop these emails' }).click();
  await expect(page.getByText('Too many tries. Wait a little, then try again.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Stop these emails' })).toBeEnabled();
});

test('no token: says so, offers the settings, sends nothing', async ({ page }, testInfo) => {
  const api = await stubSession(page, testInfo.testId);
  await open(page, '/unsubscribe');
  await expect(page.getByText('This link is missing its code.')).toBeVisible();
  await expect(page.getByRole('button')).toHaveCount(0);
  await expect(page.getByRole('link', { name: SETTINGS })).toBeVisible();
  expect(await api.seen()).toEqual([]);
});
