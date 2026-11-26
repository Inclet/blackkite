import { readFile } from 'node:fs/promises';
import { expect, test, type Page } from '@playwright/test';
import { CALENDAR_ICS } from './stubApi';

// The rest of the run blocks service workers; this file is about the installed one.
test.use({ serviceWorkers: 'allow' });

/** Open the app and wait until the PWA service worker is installed and controls the page. */
async function installServiceWorker(page: Page): Promise<void> {
  await page.goto('/');
  await page.evaluate(() => navigator.serviceWorker.ready.then(() => undefined));
  await page.waitForFunction(() => navigator.serviceWorker.controller !== null);
}

test('the installed service worker keeps the SPA fallback for app routes', async ({ page }) => {
  await installServiceWorker(page);
  const res = await page.goto('/shortlist');
  expect(res!.fromServiceWorker()).toBe(true);
  expect(res!.headers()['content-type']).toContain('text/html');
});

test('the calendar feed comes from the network, not as the cached SPA', async ({ page }) => {
  await installServiceWorker(page);
  // A calendar file is not a page: the browser downloads it. The cached SPA would render instead.
  const [res, download] = await Promise.all([
    page.waitForResponse((r) => r.url().includes('/api/calendar.ics?token=x')),
    page.waitForEvent('download'),
    page.goto('/api/calendar.ics?token=x').catch((e: Error) => expect(e.message).toContain('Download is starting')),
  ]);
  expect(res.fromServiceWorker()).toBe(false);
  expect(res.status()).toBe(200);
  expect(res.headers()['content-type']).toBe('text/calendar; charset=utf-8');
  const body = await readFile(await download.path());
  expect(body.toString('utf8')).toBe(CALENDAR_ICS);
});

test('API requests from the page are never answered by the service worker', async ({ page }) => {
  await installServiceWorker(page);
  const [res] = await Promise.all([
    page.waitForResponse((r) => r.url().includes('/api/calendar.ics')),
    page.evaluate(() => fetch('/api/calendar.ics?token=y').then((r) => r.text())),
  ]);
  expect(res.fromServiceWorker()).toBe(false);
  expect(res.headers()['content-type']).toBe('text/calendar; charset=utf-8');
});

for (const route of ['/auth/confirm', '/unsubscribe']) {
  test(`${route} comes from the network with the server's own headers`, async ({ page }) => {
    await installServiceWorker(page);
    const res = await page.goto(route);
    expect(res!.fromServiceWorker()).toBe(false);
    // The cached index.html carries strict-origin-when-cross-origin; this page's own answer does not.
    expect(res!.headers()['referrer-policy']).toBe('no-referrer');
    expect(res!.headers()['content-type']).toContain('text/html');
  });
}
