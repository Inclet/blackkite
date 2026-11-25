import { expect, test } from '@playwright/test';
import { open, stubSession } from './helpers';

/** The live screens against the stub API (stubApi.ts), through the preview server's proxy. */

const rows = '[aria-label="Opportunities"] a';

test('feed: loads from the API and ranks closing soonest first', async ({ page }, testInfo) => {
  const api = await stubSession(page, testInfo.testId);
  await page.setViewportSize({ width: 1440, height: 900 });
  await open(page, '/');
  await expect(page.getByRole('heading', { level: 1, name: 'Good afternoon, Clet' })).toBeVisible();
  await expect(page.getByText('3 sources checked this morning')).toBeVisible();
  await expect(page.locator(rows)).toHaveCount(4);
  // The stub sends the bond first; the screen ranks by date, undated last.
  await expect(page.locator(rows).nth(0)).toContainText('Logistics, transport and warehousing support');
  await expect(page.locator(rows).nth(1)).toContainText('ABH Summit');
  await expect(page.locator(rows).nth(2)).toContainText('Transition to Scale');
  await expect(page.locator(rows).nth(3)).toContainText('Five-year treasury bond');
  const urls = (await api.seen()).map((r) => `${r.method} ${r.url}`);
  expect(urls).toEqual(expect.arrayContaining(['GET /api/feed', 'GET /api/shortlist', 'GET /api/profiles']));
});

test('save persists across a reload, and shows on the shortlist', async ({ page }, testInfo) => {
  const api = await stubSession(page, testInfo.testId);
  await page.setViewportSize({ width: 1440, height: 900 });
  await open(page, '/');
  const save = page.getByRole('article').getByRole('button', { name: 'Save to shortlist' });
  await expect(save).toHaveAttribute('aria-pressed', 'false');
  await page.keyboard.press('s');
  await expect(save).toHaveAttribute('aria-pressed', 'true');
  await expect.poll(async () => (await api.seen()).filter((r) => r.method === 'PUT').map((r) => [r.url, JSON.parse(r.body)])).toEqual([
    ['/api/opportunities/wfp-logistics/state', { state: 'saved' }],
  ]);

  await page.reload();
  await expect(page.getByRole('article').getByRole('button', { name: 'Save to shortlist' })).toHaveAttribute('aria-pressed', 'true');

  // A page load of /shortlist gets the app (not the API's JSON), which then fetches /api/shortlist.
  await open(page, '/shortlist');
  await expect(page.getByRole('heading', { level: 1, name: 'Shortlist' })).toBeVisible();
  await expect(page.locator('[aria-label="Shortlist"] a')).toHaveCount(1);
  await expect(page.locator('[aria-label="Shortlist"] a')).toContainText('Logistics');
});

test('dismiss persists across a reload; a note is saved', async ({ page }, testInfo) => {
  await stubSession(page, testInfo.testId);
  await page.setViewportSize({ width: 1440, height: 900 });
  await open(page, '/');
  await page.getByLabel('Your note').fill('Ask about partner trucks');
  await page.getByRole('button', { name: 'Save note' }).click();
  await expect(page.getByText('Note saved.')).toBeVisible();
  await page.locator('h1').click();
  await page.keyboard.press('x');
  await expect(page.locator(rows)).toHaveCount(3);
  await expect.poll(async () => {
    await page.reload();
    return page.locator(rows).count();
  }).toBe(3);
  await open(page, '/o/wfp-logistics');
  await expect(page.getByText('We could not find that item.')).toBeVisible();
});

test('profile edit round trip', async ({ page }, testInfo) => {
  const api = await stubSession(page, testInfo.testId);
  await page.setViewportSize({ width: 1440, height: 900 });
  await open(page, '/profiles');
  await expect(page.getByText('Business · Tenders, Funding, Events')).toBeVisible();
  await page.getByRole('link', { name: 'Edit Ironji-Trade' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Ironji-Trade' })).toBeVisible();
  await expect(page.getByLabel('Services, separated by commas')).toHaveValue('dry freight, cold chain, last-mile distribution');

  await page.getByLabel('Smallest load (tonnes)').fill('about thirty');
  await page.getByRole('button', { name: 'Save profile' }).click();
  await expect(page.getByLabel('Smallest load (tonnes)')).toHaveAttribute('aria-invalid', 'true');
  await expect(page.getByText('Use a number, such as 100.')).toBeVisible();

  await page.getByLabel('Smallest load (tonnes)').fill('10');
  await page.getByLabel('Largest load (tonnes)').fill('30');
  await page.getByLabel('Keywords').fill('mining, quarry');
  await page.getByRole('button', { name: 'Events' }).click();
  await page.getByRole('button', { name: 'Save profile' }).click();
  await expect(page.getByText('Saved. Open items are being ranked against it again.')).toBeVisible();
  const patch = (await api.seen()).find((r) => r.method === 'PATCH');
  expect(patch?.url).toBe('/api/profiles/p1');
  expect(JSON.parse(patch!.body).data.capacity.tonnage).toEqual({ min: 10, max: 30 });

  // A page load of /profiles/p1 is the app; the values come back from the API.
  await open(page, '/profiles/p1');
  await expect(page.getByLabel('Smallest load (tonnes)')).toHaveValue('10');
  await expect(page.getByLabel('Largest load (tonnes)')).toHaveValue('30');
  await expect(page.getByLabel('Keywords')).toHaveValue('mining, quarry');
  await expect(page.getByRole('button', { name: 'Events' })).toHaveAttribute('aria-pressed', 'false');
  await expect(page.getByRole('button', { name: 'Tenders' })).toHaveAttribute('aria-pressed', 'true');
});

test('digest settings round trip', async ({ page }, testInfo) => {
  const api = await stubSession(page, testInfo.testId);
  await page.setViewportSize({ width: 390, height: 844 });
  await open(page, '/settings/digest');
  const weekly = page.getByRole('switch', { name: 'Weekly digest' });
  await expect(weekly).toHaveAttribute('aria-checked', 'true');
  // The address is the account's own, from GET /me.
  await expect(page.getByText('Every Monday, by email to clet@example.rw.')).toBeVisible();
  await weekly.click();
  await page.getByRole('button', { name: 'Strong and good fits' }).click();
  await page.getByRole('button', { name: 'Investments' }).click();
  await page.getByRole('button', { name: 'Save digest settings' }).click();
  await expect(page.getByText('Saved.', { exact: true })).toBeVisible();
  const put = (await api.seen()).find((r) => r.method === 'PUT' && r.url === '/api/digest-settings');
  expect(JSON.parse(put!.body)).toEqual({ channel: 'email', frequency: 'off', day: 'mon', alertMinFit: 'good', streams: ['investment'] });

  await page.reload();
  await expect(page.getByRole('switch', { name: 'Weekly digest' })).toHaveAttribute('aria-checked', 'false');
  await expect(page.getByRole('button', { name: 'Strong and good fits' })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('button', { name: 'Strong fits only' })).toHaveAttribute('aria-pressed', 'false');
  await expect(page.getByRole('button', { name: 'Investments' })).toHaveAttribute('aria-pressed', 'true');
});

test('first visit: no profiles, the card leads to Profiles', async ({ page }, testInfo) => {
  await stubSession(page, testInfo.testId, { profiles: [] });
  await page.setViewportSize({ width: 390, height: 844 });
  await open(page, '/');
  await expect(page.getByText('Tell Blackkite what you do')).toBeVisible();
  await page.getByRole('button', { name: 'Set up a profile' }).click();
  await expect(page).toHaveURL(/\/profiles$/);
  await expect(page.getByRole('button', { name: 'Add a business profile' })).toBeVisible();
});

test('nothing new: an empty feed', async ({ page }, testInfo) => {
  await stubSession(page, testInfo.testId, { items: [] });
  await page.setViewportSize({ width: 1440, height: 900 });
  await open(page, '/');
  await expect(page.getByText('Nothing new since yesterday')).toBeVisible();
  await expect(page.getByText('All 3 sources were checked this morning. Your shortlist has nothing closing this month.')).toBeVisible();
});
