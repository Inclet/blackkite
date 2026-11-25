import { expect, test } from '@playwright/test';
import { anonymousSeen, open, stubSession } from './helpers';

test('sign-in link: the token goes through the proxy, leaves the address bar, and the redirect is followed', async ({ page }, testInfo) => {
  // The run's stub API (stubApi.ts); this test's requests are logged under its own session.
  const api = await stubSession(page, testInfo.testId);
  await page.setViewportSize({ width: 390, height: 844 });
  await open(page, '/auth/confirm#token=abc');
  await expect(page.getByRole('heading', { level: 1, name: 'Sign in to Blackkite' })).toBeVisible();
  // The page itself is a web route, never proxied.
  expect(await api.seen()).toEqual([]);
  await expect.poll(() => page.url()).toMatch(/\/auth\/confirm$/);
  expect(page.url()).not.toContain('abc');
  await expect(page.locator('meta[name="referrer"]')).toHaveAttribute('content', 'no-referrer');

  await page.getByRole('button', { name: 'Continue to sign in' }).click();
  await expect.poll(() => new URL(page.url()).pathname).toBe('/shortlist');

  const seen = (await api.seen()).filter((r) => r.url.startsWith('/auth/'));
  expect(seen).toHaveLength(1);
  const [req] = seen;
  expect(req!.method).toBe('POST');
  expect(req!.url).toBe('/auth/verify');
  expect(req!.contentType).toContain('application/json');
  expect(JSON.parse(req!.body)).toEqual({ token: 'abc' });
});

test('no session: the feed shows the sign-in screen, which posts the address to /auth/request-link', async ({ page }) => {
  // A unique address, so this test finds its own request in the shared anonymous log.
  const email = `clet+${Date.now()}-${Math.random().toString(36).slice(2)}@example.rw`;
  await page.setViewportSize({ width: 390, height: 844 });
  await open(page, '/');
  await expect(page.getByRole('heading', { level: 1, name: 'Sign in to Blackkite' })).toBeVisible();
  await page.getByLabel('Email address').fill(email);
  await page.getByRole('button', { name: 'Email me a sign-in link' }).click();
  await expect(page.getByText('Check your email for a link.')).toBeVisible();
  const mine = (await anonymousSeen()).filter((r) => r.url === '/auth/request-link' && r.body.includes(email));
  expect(mine).toHaveLength(1);
  expect(mine[0]!.method).toBe('POST');
  expect(mine[0]!.contentType).toContain('application/json');
  expect(JSON.parse(mine[0]!.body)).toEqual({ email });
});
