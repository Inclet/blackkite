import { expect, test } from '@playwright/test';
import { interactiveBoxes, open, stubSession } from './helpers';

/** M4 against the stub API (stubApi.ts + stubM4.ts): calendar, private items, the full detail, feed filters. */

const rows = '[aria-label="Opportunities"] a';
const desktop = { width: 1440, height: 900 };
const phone = { width: 390, height: 844 };

test('calendar: month grid, today, next month, show and saved only, list view, keyboard, opens the item', async ({ page }, testInfo) => {
  const api = await stubSession(page, testInfo.testId, { states: { 't2s-call': 'saved' } });
  await page.setViewportSize(desktop);
  await open(page, '/calendar');
  const grid = page.getByRole('table', { name: 'November 2026' });
  await expect(grid).toBeVisible();
  await expect(grid.locator('[aria-current="date"]')).toContainText('24');
  const wfp = grid.getByRole('link', { name: /Logistics, transport/ });
  await expect(wfp).toContainText('Closes 5pm');
  await expect(wfp).toContainText('Strong');

  await page.getByRole('button', { name: 'Next month' }).click();
  const dec = page.getByRole('table', { name: 'December 2026' });
  await expect(dec.getByRole('link', { name: /ABH Summit/ })).toHaveCount(2);
  await expect(dec.getByRole('link', { name: /ABH Summit/ }).first()).toContainText('Starts');
  await expect(page).toHaveURL(/month=2026-12/);

  // Keyboard: Right from 1 Dec reaches 2 Dec, Right again reaches 7 Dec.
  await dec.getByRole('link', { name: /ABH Summit/ }).first().focus();
  await page.keyboard.press('ArrowRight');
  await expect(dec.getByRole('link', { name: /ABH Summit/ }).nth(1)).toBeFocused();
  await page.keyboard.press('ArrowRight');
  await expect(dec.getByRole('link', { name: /Transition to Scale/ })).toBeFocused();

  await page.getByRole('button', { name: 'Events' }).click();
  await expect(dec.getByRole('link', { name: /Transition to Scale/ })).toHaveCount(0);
  await page.getByRole('button', { name: 'All', exact: true }).click();
  await page.getByRole('button', { name: 'Saved only' }).click();
  await expect(dec.getByRole('link')).toHaveCount(1);
  await expect.poll(async () => (await api.seen()).map((r) => r.url)).toContain('/api/calendar?from=2026-12-01&to=2026-12-31&kind=all&saved=true');

  await page.getByRole('button', { name: 'List', exact: true }).click();
  const list = page.getByRole('list', { name: 'Days' });
  await expect(list.getByRole('heading', { level: 3 })).toHaveText(['Monday 7 December 2026']);
  await list.getByRole('link', { name: /Transition to Scale/ }).click();
  await expect(page).toHaveURL(/\/o\/t2s-call$/);
  await expect(page.getByRole('article').getByRole('heading', { name: 'Transition to Scale research and innovation call' })).toBeVisible();
});

test('calendar on a phone: the list by day, today tagged', async ({ page }, testInfo) => {
  await stubSession(page, testInfo.testId);
  await page.setViewportSize(phone);
  await open(page, '/calendar');
  await expect(page.getByRole('table')).toHaveCount(0);
  const list = page.getByRole('list', { name: 'Days' });
  await expect(list.getByRole('heading', { level: 3 })).toHaveText(['Monday 30 November 2026']);
  await expect(list.getByRole('link')).toContainText('Closes 5pm');
  await expect(page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Calendar' })).toHaveAttribute('aria-current', 'page');
});

test('calendar feed link: copy, then stop it with a confirm', async ({ page, context }, testInfo) => {
  const api = await stubSession(page, testInfo.testId);
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await page.setViewportSize(desktop);
  await open(page, '/calendar');
  const card = page.getByRole('region', { name: 'Add to your calendar app' });
  await expect(card).toContainText('never shows your notes, scores or profiles');
  const field = card.getByLabel('Your calendar link');
  await expect(field).toHaveValue(/token=cal-u1-v1$/);
  await card.getByRole('button', { name: 'Copy link' }).click();
  await expect(card.getByText('Link copied.')).toBeVisible();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toMatch(/token=cal-u1-v1$/);

  await card.getByRole('button', { name: 'Stop this link' }).click();
  await card.getByRole('button', { name: 'Keep this link' }).click();
  await expect(card.getByRole('button', { name: 'Stop this link' })).toBeFocused();
  await card.getByRole('button', { name: 'Stop this link' }).click();
  await card.getByRole('button', { name: 'Stop it and make a new link' }).click();
  await expect(card.getByText('The old link no longer works.', { exact: false })).toBeVisible();
  await expect(field).toHaveValue(/token=cal-u1-v2$/);
  expect((await api.seen()).filter((r) => r.method === 'POST').map((r) => r.url)).toEqual(['/api/calendar/feed-link/rotate']);
});

async function addItem(page: import('@playwright/test').Page, title: string) {
  await open(page, '/');
  await page.getByRole('button', { name: 'Add an item' }).click();
  await expect(page).toHaveURL(/\/items\/new$/);
  const form = page.getByRole('form', { name: 'Add an item' });
  await form.getByRole('button', { name: 'Tenders' }).click();
  await form.getByLabel('Title').fill(title);
  await form.getByLabel('Organisation (optional)').fill('Kigali Bus');
  await form.getByLabel('Deadline (optional)').fill('10 Dec 2026, 5pm');
  await form.getByLabel('Value (optional)').fill('2,000,000');
  await form.getByLabel('Link (optional)').fill('https://example.rw/notice');
  await form.getByRole('button', { name: 'Add the item' }).click();
  await expect(page).toHaveURL(/\/o\/own-1$/);
}

test('private item: create, edit, consent, admin publish locks it', async ({ page }, testInfo) => {
  const api = await stubSession(page, testInfo.testId);
  await page.setViewportSize(desktop);
  await addItem(page, 'Fuel supply');
  const pane = page.getByRole('article');
  await expect(pane.getByRole('heading', { name: 'Fuel supply' })).toBeVisible();
  await expect(pane.getByText('Private: only you can see this')).toBeVisible();
  await expect(pane).toContainText('You added this item yourself');
  const created = (await api.seen()).find((r) => r.method === 'POST' && r.url === '/api/items')!;
  expect(JSON.parse(created.body)).toMatchObject({ stream: 'tender', title: 'Fuel supply', deadline: '2026-12-10T17:00', value: 2000000, currency: 'RWF' });

  await pane.getByRole('button', { name: 'Edit: Fuel supply' }).click();
  await expect(page.getByLabel('Title')).toHaveValue('Fuel supply');
  await expect(page.getByLabel('Deadline (optional)')).toHaveValue('10 Dec 2026, 5pm');
  await page.getByLabel('Title').fill('Fuel supply, phase 2');
  await page.getByRole('button', { name: 'Save changes' }).click();
  await expect(page.getByRole('article').getByRole('heading', { name: 'Fuel supply, phase 2' })).toBeVisible();

  const share = page.getByRole('switch', { name: 'Let an admin make this public' });
  await expect(share).toHaveAttribute('aria-checked', 'false');
  await share.click();
  await expect(share).toHaveAttribute('aria-checked', 'true');
  await expect(page.getByText('Admins may now make this item public.')).toBeVisible();

  // The stub session is also an admin.
  await open(page, '/admin/shareable');
  const card = page.getByRole('region', { name: 'Fuel supply, phase 2' });
  await card.getByRole('button', { name: 'Make public: Fuel supply, phase 2' }).click();
  await expect(page.getByText('Made public: Fuel supply, phase 2.')).toBeVisible();
  await expect(page.getByText('No private items are waiting to be made public.')).toBeVisible();

  await open(page, '/o/own-1');
  await expect(page.getByText('Public: an admin published it with your consent')).toBeVisible();
  await expect(page.getByRole('switch', { name: 'Let an admin make this public' })).toBeDisabled();
  await expect(page.getByRole('region', { name: 'History' })).toContainText('an admin made it public');
});

test('private item: delete with a confirm; a refused publish is a plain sentence', async ({ page }, testInfo) => {
  await stubSession(page, testInfo.testId);
  await page.setViewportSize(phone);
  await addItem(page, 'Market stalls');
  await page.getByRole('switch', { name: 'Let an admin make this public' }).click();
  await expect(page.getByText('Admins may now make this item public.')).toBeVisible();
  await open(page, '/admin/shareable');
  await expect(page.getByRole('region', { name: 'Market stalls' })).toBeVisible();
  // The owner withdraws consent meanwhile (another tab).
  await page.evaluate(() => fetch('/api/items/own-1/share-consent', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ allow: false }) }));
  await page.getByRole('button', { name: 'Make public: Market stalls' }).click();
  await expect(page.getByText('Market stalls: The owner no longer allows this, so it stays private.')).toBeVisible();

  await open(page, '/o/own-1');
  await page.getByRole('button', { name: 'Delete: Market stalls' }).click();
  await page.getByRole('button', { name: 'Delete it' }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.locator('main a', { hasText: 'Market stalls' })).toHaveCount(0);
  await open(page, '/o/own-1');
  await expect(page.getByRole('heading', { name: 'We could not find that item' })).toBeVisible();
});

test('detail sections: open in the desktop pane, closed behind buttons on the phone', async ({ page }, testInfo) => {
  await stubSession(page, testInfo.testId);
  await page.setViewportSize(desktop);
  await open(page, '/o/wfp-logistics');
  const details = page.getByRole('region', { name: 'Details' });
  await expect(details).toContainText('30 Nov 2026, 5pm — from the notice: Closing date: 30 November 2026, 17:00 Kigali time');
  await expect(details).toContainText('FRW 120,000,000');
  const sources = page.getByRole('region', { name: 'Sources' });
  await expect(sources.getByRole('link', { name: 'Open Job in Rwanda, tenders (opens in a new tab)' })).toHaveAttribute('href', 'https://www.jobinrwanda.com/jobs/tender');
  await expect(sources).toContainText('First seen 9 Nov 2026 · last seen 24 Nov 2026');
  await expect(page.getByRole('region', { name: 'Documents' })).toContainText('wfp-logistics-rfp.pdf');
  await expect(page.getByRole('region', { name: 'History' })).toContainText('20 Nov 2026: the deadline moved from 28 Nov 2026, 5pm to 30 Nov 2026, 5pm.');

  await page.setViewportSize(phone);
  const toggle = page.getByRole('button', { name: 'Details', exact: true });
  await expect(toggle).toHaveAccessibleName('Details');
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await expect(page.getByText('FRW 120,000,000', { exact: true })).toBeHidden();
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-expanded', 'true');
  await expect(page.getByText('FRW 120,000,000', { exact: true })).toBeVisible();
});

test('feed filters round-trip in the URL, survive a reload, and clear', async ({ page }, testInfo) => {
  const api = await stubSession(page, testInfo.testId);
  await page.setViewportSize(desktop);
  await open(page, '/');
  await expect(page.locator(rows)).toHaveCount(4);
  await page.getByRole('button', { name: 'Filters' }).click();
  const panel = page.getByRole('region', { name: 'Filter the feed' });
  await panel.getByRole('button', { name: 'Good and up' }).click();
  await panel.getByRole('button', { name: 'This week' }).click();
  await expect(page).toHaveURL(/\?fit=good&window=7$/);
  await expect(page.locator(rows)).toHaveCount(1);
  await expect.poll(async () => (await api.seen()).map((r) => r.url)).toContain('/api/feed?window=7&fit=good');

  await page.reload();
  await expect(page.locator(rows)).toHaveCount(1);
  await expect(page.getByRole('button', { name: 'Filters (2)' })).toBeVisible();
  await page.getByRole('button', { name: 'Remove filter Fit: Good and up' }).click();
  await expect(page).toHaveURL(/\?window=7$/);
  await expect(page.locator(rows)).toHaveCount(2);
  await page.getByRole('button', { name: 'Clear filters' }).click();
  await expect(page).toHaveURL(/\/o\/[^?]+$|\/$/);
  await expect(page.locator(rows)).toHaveCount(4);
});

for (const width of [360, 1440]) {
  test(`${width}px: an own item's controls reflow with 44px targets and no overlaps`, async ({ page }, testInfo) => {
    await stubSession(page, testInfo.testId);
    await page.setViewportSize({ width, height: 900 });
    await addItem(page, 'Fuel supply');
    await page.getByRole('button', { name: 'Delete: Fuel supply' }).click();
    await expect(page.getByRole('button', { name: 'Delete it' })).toBeVisible();
    const { scrollWidth, innerWidth } = await page.evaluate(() => ({ scrollWidth: document.scrollingElement!.scrollWidth, innerWidth: window.innerWidth }));
    expect(scrollWidth).toBeLessThanOrEqual(innerWidth);
    const boxes = (await interactiveBoxes(page)).filter((b) => !b.floating);
    for (const b of boxes) {
      expect(Math.max(b.h, b.hitH), `${b.label} height`).toBeGreaterThanOrEqual(43.5);
      expect(Math.max(b.w, b.hitW), `${b.label} width`).toBeGreaterThanOrEqual(43.5);
    }
    for (let i = 0; i < boxes.length; i++) {
      for (let j = i + 1; j < boxes.length; j++) {
        const a = boxes[i]!;
        const c = boxes[j]!;
        const ox = Math.min(a.x + a.w, c.x + c.w) - Math.max(a.x, c.x);
        const oy = Math.min(a.y + a.h, c.y + c.h) - Math.max(a.y, c.y);
        expect(ox > 0.5 && oy > 0.5, `${a.label} overlaps ${c.label}`).toBe(false);
      }
    }
  });
}
