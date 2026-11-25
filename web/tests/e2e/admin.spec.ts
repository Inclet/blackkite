import { expect, test } from '@playwright/test';
import { open, stubSession } from './helpers';

/** Sources (members) and the admin screens, against the stub API (stubApi.ts) through the preview proxy. */

const DESKTOP = { width: 1440, height: 900 };
const PHONE = { width: 390, height: 844 };

test('member: mute a source and suggest one', async ({ page }, testInfo) => {
  const api = await stubSession(page, testInfo.testId, { role: 'member' });
  await page.setViewportSize(DESKTOP);
  await open(page, '/sources');
  const list = page.getByRole('region', { name: 'Sources Blackkite checks' });
  // Active sources only, health in words.
  await expect(list.getByText('Job in Rwanda, tenders')).toBeVisible();
  await expect(list.getByText('Health: Some problems')).toBeVisible();
  await expect(list.getByText('Umucyo e-procurement')).toHaveCount(0);
  // A member has no Admin entry.
  await expect(page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Admin' })).toHaveCount(0);

  const sw = list.getByRole('switch', { name: 'Mute RSE bond market' });
  await sw.click();
  await expect(sw).toHaveAttribute('aria-checked', 'true');
  await expect(page.getByText('Muted RSE bond market. Your feed is being updated.')).toBeVisible();
  await page.reload();
  await expect(page.getByRole('switch', { name: 'Mute RSE bond market' })).toHaveAttribute('aria-checked', 'true');

  const form = page.getByRole('form', { name: 'Suggest a source' });
  await form.getByLabel('Web address').fill('https://www.impacthub.rw/events');
  await form.getByLabel('What it covers').fill('Impact Hub Kigali events');
  await form.getByLabel('Why it is useful').fill('Startup events are listed here first');
  await form.getByRole('button', { name: 'Send suggestion' }).click();
  await expect(page.getByText('Thanks. An admin will look at it; you can follow it below.')).toBeVisible();
  const yours = page.getByRole('region', { name: 'Your suggestions' });
  await expect(yours.getByText('https://www.impacthub.rw/events')).toBeVisible();
  await expect(yours.getByText('Waiting for review')).toBeVisible();

  const sent = (await api.seen()).filter((r) => r.method !== 'GET').map((r) => [r.method, r.url, r.body ? JSON.parse(r.body) : null]);
  expect(sent).toEqual([
    ['POST', '/api/sources/src-rse/mute', null],
    ['POST', '/api/source-suggestions', { url: 'https://www.impacthub.rw/events', note: 'Covers: Impact Hub Kigali events\nWhy it is useful: Startup events are listed here first' }],
  ]);
});

test('admin: create a source, test run preview (nothing saved), save as testing', async ({ page }, testInfo) => {
  const api = await stubSession(page, testInfo.testId);
  await page.setViewportSize(DESKTOP);
  await open(page, '/sources');
  // Admins get an Admin entry after the board's five.
  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Admin' }).click();
  await page.getByRole('link', { name: 'Sources' }).last().click();
  await expect(page).toHaveURL(/\/admin\/sources$/);
  await expect(page.getByRole('region', { name: 'Testing' }).getByText('Needs 2 good runs since the last config change: 1 so far.')).toBeVisible();
  await page.getByRole('button', { name: 'Add a source' }).click();
  await expect(page).toHaveURL(/\/admin\/sources\/new$/);

  const form = page.getByRole('form', { name: 'New source' });
  await form.getByLabel('Name', { exact: true }).fill('NCST calls');
  await form.getByLabel('Home page').fill('https://www.ncst.gov.rw/');
  await form.getByRole('button', { name: 'Funding' }).click();
  await form.getByRole('button', { name: 'The issuer itself' }).click();
  // The config form comes from GET /api/admin/collector-types.
  await form.getByRole('button', { name: 'Web page list' }).click();
  await form.getByLabel('List url').fill('https://www.ncst.gov.rw/calls');
  await form.getByLabel('Selectors: item', { exact: true }).fill('article');
  await form.getByLabel('Selectors: title', { exact: true }).fill('h2 a');

  await page.getByRole('button', { name: 'Test run' }).click();
  const preview = page.getByRole('region', { name: 'Test run results' });
  await expect(preview.getByText('Call for applied research proposals')).toBeVisible();
  await expect(preview.getByText('Published 20 Nov 2026 · Closes 15 Dec 2026')).toBeVisible();
  await expect(preview.getByText('Nothing was saved: this run wrote no items and no run history.')).toBeVisible();
  expect((await api.seen()).some((r) => r.method === 'POST' && r.url === '/api/admin/sources')).toBe(false);

  await form.getByRole('button', { name: 'Save as testing' }).click();
  await expect(page).toHaveURL(/\/admin\/sources\/src-\d+$/);
  await expect(page.getByText('Saved as testing. It runs on its schedule')).toBeVisible();
  await expect(page.getByRole('heading', { level: 1, name: 'NCST calls' })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Source status' }).getByText('Testing', { exact: true })).toBeVisible();

  const posts = (await api.seen()).filter((r) => r.method === 'POST').map((r) => [r.url, JSON.parse(r.body)]);
  expect(posts).toEqual([
    [
      '/api/admin/sources/test-run',
      { collectorType: 'html_list', config: { list_url: 'https://www.ncst.gov.rw/calls', selectors: { item: 'article', title: 'h2 a' } }, homeUrl: 'https://www.ncst.gov.rw/', streams: ['funding'], rateLimit: null },
    ],
    [
      '/api/admin/sources',
      {
        name: 'NCST calls',
        homeUrl: 'https://www.ncst.gov.rw/',
        publisher: null,
        streams: ['funding'],
        kind: 'original',
        collectorType: 'html_list',
        config: { list_url: 'https://www.ncst.gov.rw/calls', selectors: { item: 'article', title: 'h2 a' } },
        schedule: null,
        rateLimit: null,
        accessNote: null,
      },
    ],
  ]);
});

test('admin: promotion is refused with the gate explained; run history and error log', async ({ page }, testInfo) => {
  await stubSession(page, testInfo.testId);
  await page.setViewportSize(DESKTOP);
  await open(page, '/admin/sources/src-umucyo');
  const status = page.getByRole('region', { name: 'Source status' });
  await expect(status.getByText(/Needs 2 good runs since the last config change: 1 so far\./)).toBeVisible();
  await status.getByRole('button', { name: 'Make active' }).click();
  await expect(status.getByText('Not changed: it stays testing. Needs 2 good runs since the last config change: 1 so far.')).toBeVisible();
  await expect(page.getByRole('region', { name: 'Error log' }).getByText('HTTP 503 from www.umucyo.gov.rw')).toBeVisible();
  await expect(page.getByRole('region', { name: 'Run history' }).getByText('9 found · 2 new')).toBeVisible();
  await expect(page.getByRole('region', { name: 'Status history' }).getByText('Created as testing')).toBeVisible();
  // Every collector is built now: JSON API renders its mapping and pagination fields, with no "not built" note.
  const form = page.getByRole('form', { name: 'Umucyo e-procurement' });
  await form.getByRole('button', { name: 'JSON API' }).click();
  await expect(form.getByLabel('Mapping: title', { exact: true })).toBeVisible();
  await expect(form.getByLabel('Pagination (optional)')).toBeVisible();
  await expect(page.getByText(/This collector is not built yet/)).toHaveCount(0);
});

test('admin: accept a suggestion, then create a source from it, prefilled', async ({ page }, testInfo) => {
  const api = await stubSession(page, testInfo.testId);
  await page.setViewportSize(DESKTOP);
  await open(page, '/admin/suggestions');
  const waiting = page.getByRole('region', { name: 'Waiting for review' });
  await expect(waiting.getByText('https://www.rdb.rw/calls')).toBeVisible();
  await waiting.getByRole('button', { name: 'Accept https://www.rdb.rw/calls' }).click();
  await expect(page.getByText('Accepted https://www.rdb.rw/calls.')).toBeVisible();
  await page.getByRole('button', { name: 'Create source from this: https://www.rdb.rw/calls' }).click();
  await expect(page).toHaveURL(/\/admin\/sources\/new\?suggestion=sg-1$/);
  await expect(page.getByRole('region', { name: 'From a member’s suggestion' }).getByText('Why it is useful: funding calls appear here first')).toBeVisible();
  const form = page.getByRole('form', { name: 'New source' });
  await expect(form.getByLabel('Home page')).toHaveValue('https://www.rdb.rw/calls');
  await form.getByLabel('Name', { exact: true }).fill('RDB calls');
  await form.getByRole('button', { name: 'Funding' }).click();
  await form.getByRole('button', { name: 'News' }).click();
  await form.getByRole('button', { name: 'RSS feed' }).click();
  await form.getByLabel('Feed url').fill('https://www.rdb.rw/feed');
  await form.getByRole('button', { name: 'Save as testing' }).click();
  await expect(page).toHaveURL(/\/admin\/sources\/src-\d+$/);
  const created = (await api.seen()).find((r) => r.method === 'POST' && r.url === '/api/admin/sources')!;
  expect(JSON.parse(created.body)).toMatchObject({ suggestionId: 'sg-1', homeUrl: 'https://www.rdb.rw/calls', collectorType: 'rss', config: { feed_url: 'https://www.rdb.rw/feed' } });
});

test('admin: mark a needs-review item reviewed', async ({ page }, testInfo) => {
  const api = await stubSession(page, testInfo.testId);
  await page.setViewportSize(PHONE);
  await open(page, '/admin/review');
  const item = page.getByRole('region', { name: 'Construction of a cold-storage warehouse' });
  await expect(item.getByText('Job in Rwanda says 3 Dec 2026; The New Times says 10 Dec 2026.')).toBeVisible();
  await item.getByRole('button', { name: 'Mark reviewed: Construction of a cold-storage warehouse' }).click();
  await expect(page.getByText('Marked reviewed: Construction of a cold-storage warehouse.')).toBeVisible();
  await expect(page.getByText('Nothing needs review.')).toBeVisible();
  expect((await api.seen()).filter((r) => r.method === 'POST').map((r) => r.url)).toEqual(['/api/admin/catalogue/op-warehouse/review']);
});

test('admin: invite a user, then deactivate one with a confirm step', async ({ page }, testInfo) => {
  const api = await stubSession(page, testInfo.testId);
  await page.setViewportSize(DESKTOP);
  await open(page, '/admin/users');
  const form = page.getByRole('form', { name: 'Invite someone' });
  await form.getByLabel('Email address').fill('amina@example.rw');
  await form.getByRole('button', { name: 'Send invite' }).click();
  await expect(form.getByText('That address already has an account.')).toBeVisible();
  await form.getByLabel('Email address').fill('grace@example.rw');
  await form.getByRole('button', { name: 'Send invite' }).click();
  await expect(form.getByText('Invite sent to grace@example.rw.')).toBeVisible();
  await expect(page.getByRole('region', { name: 'Invites' }).getByText('grace@example.rw')).toBeVisible();

  const accounts = page.getByRole('region', { name: 'Accounts' });
  await expect(accounts.getByRole('button', { name: 'Deactivate clet@example.rw' })).toHaveCount(0);
  await accounts.getByRole('button', { name: 'Deactivate amina@example.rw' }).click();
  await accounts.getByRole('button', { name: 'Deactivate this account' }).click();
  await expect(page.getByText('amina@example.rw is deactivated.')).toBeVisible();
  expect((await api.seen()).filter((r) => r.method === 'POST').map((r) => r.url)).toEqual(['/api/admin/invites', '/api/admin/invites', '/api/admin/users/u2/deactivate']);
});

test('admin: change a member to admin', async ({ page }, testInfo) => {
  const api = await stubSession(page, testInfo.testId);
  await page.setViewportSize(PHONE);
  await open(page, '/admin/users');
  const accounts = page.getByRole('region', { name: 'Accounts' });
  await expect(accounts.getByText('clet@example.rw · Joined 1 Nov 2026 · Last signed in 24 Nov 2026')).toBeVisible();
  await accounts.getByRole('button', { name: 'Make admin: amina@example.rw' }).click();
  await expect(page.getByText('amina@example.rw is now an admin.')).toBeVisible();
  const patch = (await api.seen()).find((r) => r.method === 'PATCH')!;
  expect([patch.url, JSON.parse(patch.body)]).toEqual(['/api/admin/users/u2', { role: 'admin' }]);
});

for (const route of ['/admin', '/admin/sources', '/admin/sources/new', '/admin/sources/src-umucyo', '/admin/suggestions', '/admin/review', '/admin/users']) {
  test(`non-admin: ${route} says "This page is for admins." and calls no admin route`, async ({ page }, testInfo) => {
    const api = await stubSession(page, testInfo.testId, { role: 'member' });
    await page.setViewportSize(DESKTOP);
    await open(page, route);
    await expect(page.getByText('This page is for admins.')).toBeVisible();
    await expect(page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Admin' })).toHaveCount(0);
    expect((await api.seen()).filter((r) => r.url.startsWith('/api/admin'))).toEqual([]);
  });
}

test('non-admin phone More has no Admin link; an admin\'s does', async ({ page }, testInfo) => {
  await stubSession(page, testInfo.testId, { role: 'member' });
  await page.setViewportSize(PHONE);
  await open(page, '/more');
  await expect(page.getByRole('link', { name: 'Account' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Admin' })).toHaveCount(0);
  await stubSession(page, `${testInfo.testId}-admin`);
  await open(page, '/more');
  await expect(page.getByRole('link', { name: 'Admin' })).toBeVisible();
});
