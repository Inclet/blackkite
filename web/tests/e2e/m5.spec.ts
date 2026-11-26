import { expect, test } from '@playwright/test';
import { colours, contrastRatio, open, stubSession } from './helpers';
import { ITEM_CATEGORIES } from './stubM5';

/** M5 against the stub API (stubApi.ts + stubM5.ts): benchmarks, a category's awards, the detail line, Coming up, the second user. */

const desktop = { width: 1440, height: 900 };
const phone = { width: 390, height: 844 };

test('benchmarks: categories in plain words, period and organisation filters, one currency per line', async ({ page }, testInfo) => {
  const api = await stubSession(page, testInfo.testId);
  await page.setViewportSize(desktop);
  await open(page, '/');
  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Benchmarks' }).click();
  await expect(page).toHaveURL(/\/benchmarks$/);
  const list = page.getByRole('region', { name: 'Categories' });
  await expect(list).toContainText('Freight and transport');
  await expect(list).toContainText('Most awards were between FRW 4.2M and FRW 6.7M; the middle one was FRW 5.5M (12 awards). Usually 3 bidders.');
  await expect(list).toContainText('Only 2 awards so far — not enough to show a range.');
  await expect(list).toContainText('Software and IT services (FRW)');
  await expect(list).toContainText('Software and IT services (USD)');
  await expect(list).toContainText('Most awards were between USD');
  expect((await api.seen()).map((r) => r.url)).toContain('/api/benchmarks?from=2025-11-24&to=2026-11-24');

  await page.getByRole('button', { name: 'All', exact: true }).click();
  await expect(list).toContainText('(23 awards)');
  await expect(page).toHaveURL(/period=all/);

  await page.getByRole('textbox', { name: 'Buying organisation' }).fill('City of Kigali');
  await page.getByRole('button', { name: 'Show', exact: true }).click();
  await expect(list).toContainText('Only 1 award so far — not enough to show a range.');
  await expect(page).toHaveURL(/entity=City/);
  await page.getByRole('button', { name: 'Clear', exact: true }).click();
  await expect(list).toContainText('(23 awards)');
});

test('a category: awards, bidders behind a disclosure, notice in a new tab, paging', async ({ page }, testInfo) => {
  const api = await stubSession(page, testInfo.testId);
  await page.setViewportSize(desktop);
  await open(page, '/benchmarks');
  await page.getByRole('link', { name: 'Freight and transport: see the awards' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Freight and transport' })).toBeVisible();
  const list = page.getByRole('region', { name: 'Awarded contracts' });
  await expect(list).toContainText('Awards 1–20 of 23');
  await expect(list).toContainText('Won by Kivu Haulage Ltd at FRW 3,000,000');

  const toggle = list.getByRole('button', { name: /: show the 3 bidders$/ }).first();
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await toggle.focus();
  await page.keyboard.press('Enter');
  await expect(list.getByRole('button', { name: /: hide the 3 bidders$/ }).first()).toHaveAttribute('aria-expanded', 'true');
  await expect(list.getByRole('list', { name: /^Bidders: / }).first()).toContainText('Hills Transport — FRW');

  const notice = list.getByRole('link', { name: /: open the notice \(opens in a new tab\)$/ }).first();
  await expect(notice).toHaveAttribute('target', '_blank');
  await expect(notice).toHaveAttribute('href', /^https:\/\/www\.umucyo\.gov\.rw\/awards\/freight-/);

  await page.getByRole('button', { name: 'More awards' }).click();
  await expect(list).toContainText('Awards 21–23 of 23');
  await expect(page).toHaveURL(/page=2/);
  await expect(page.getByRole('heading', { level: 1 })).toBeFocused();
  expect((await api.seen()).map((r) => r.url)).toContain('/api/benchmarks/freight?limit=20&offset=20');
  await page.getByRole('button', { name: 'Previous awards' }).click();
  await expect(list).toContainText('Awards 1–20 of 23');
  await page.getByRole('link', { name: 'Back to benchmarks' }).click();
  await expect(page).toHaveURL(/\/benchmarks(\?.*)?$/);
});

test('tender detail: "Similar awarded contracts" in the pane and on the phone page, linking to the category', async ({ page }, testInfo) => {
  // detail.benchmark is on only when seeded (the dumped OpportunityOut does not have it yet; stubApi.ts).
  await stubSession(page, testInfo.testId, { itemCategories: ITEM_CATEGORIES });
  await page.setViewportSize(desktop);
  await open(page, '/o/wfp-logistics');
  const pane = page.getByRole('article');
  await expect(pane.getByText('Similar awarded contracts')).toBeVisible();
  const line = pane.getByRole('link', { name: /^Similar contracts were usually awarded between FRW [\d.]+M and FRW [\d.]+M \(23 awards\)\.$/ });
  await expect(line).toHaveAttribute('href', '/benchmarks/freight');
  // Contrast: the link text (graphite on white) at least 4.5:1.
  const { fg, bg } = await colours(page, 'text=Similar contracts were usually awarded');
  expect(contrastRatio(fg, bg)).toBeGreaterThanOrEqual(4.5);

  // Not on other streams.
  await open(page, '/o/t2s-call');
  await expect(page.getByRole('article').getByRole('heading', { name: 'Transition to Scale research and innovation call' })).toBeVisible();
  await expect(page.getByText('Similar awarded contracts')).toHaveCount(0);

  await page.setViewportSize(phone);
  await open(page, '/o/wfp-logistics');
  await page.getByRole('link', { name: /^Similar contracts were usually awarded/ }).click();
  await expect(page).toHaveURL(/\/benchmarks\/freight$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Freight and transport' })).toBeVisible();
});

test('Coming up: planned tenders on the Calendar and the Shortlist; empty wording', async ({ page }, testInfo) => {
  await stubSession(page, testInfo.testId);
  await page.setViewportSize(desktop);
  for (const route of ['/calendar', '/shortlist']) {
    await open(page, route);
    const card = page.getByRole('region', { name: 'Coming up' });
    await expect(card).toContainText('Rwanda Agriculture Board');
    await expect(card).toContainText('Open competitive bidding · Estimated FRW 45M · Planned for January to March 2027');
    await expect(card).toContainText('Matches Ironji-Trade');
    await expect(card).toContainText('Restricted tender · Planned for March 2027');
    await expect(card).toContainText('Matches AI lab');
    await expect(card.getByRole('link', { name: 'Rwanda Agriculture Board: open the plan (opens in a new tab)' })).toHaveAttribute('target', '_blank');
  }
  await stubSession(page, `${testInfo.testId}-empty`, { plans: [] });
  await page.setViewportSize(phone);
  await open(page, '/calendar');
  await expect(page.getByRole('region', { name: 'Coming up' })).toContainText('No planned tenders match your profiles yet.');
});

test('phone More reaches Benchmarks', async ({ page }, testInfo) => {
  await stubSession(page, testInfo.testId, { role: 'member' });
  await page.setViewportSize(phone);
  await open(page, '/more');
  await page.getByRole('link', { name: 'Benchmarks' }).click();
  await expect(page).toHaveURL(/\/benchmarks$/);
  await expect(page.getByRole('region', { name: 'Categories' })).toContainText('Freight and transport');
});

test('second user: a member with an NGO profile and a personal profile, through the flow', async ({ page }, testInfo) => {
  const api = await stubSession(page, testInfo.testId, { role: 'member', userName: 'Amina', profiles: [], states: {} });
  await page.setViewportSize(desktop);
  await open(page, '/profiles');
  // A member: no Admin link, Benchmarks is there.
  const nav = page.getByRole('navigation', { name: 'Main' });
  await expect(nav.getByRole('link', { name: 'Admin' })).toHaveCount(0);
  await expect(nav.getByRole('link', { name: 'Benchmarks' })).toBeVisible();

  await page.getByRole('button', { name: 'Add a business profile' }).click();
  await page.getByLabel('Profile name').fill('Health NGO');
  const kind = page.getByRole('group', { name: 'Type of organisation' });
  await kind.getByRole('button', { name: 'NGO or non-profit' }).click();
  await expect(kind.getByRole('button', { name: 'NGO or non-profit' })).toHaveAttribute('aria-pressed', 'true');
  await page.getByLabel('Services, separated by commas').fill('community health, training');
  await page.getByLabel('Sectors you work in, separated by commas').fill('health');
  await page.getByLabel('Other places you work, separated by commas').fill('Musanze, Rubavu');
  await page.getByRole('button', { name: 'Add profile' }).click();
  await expect(page).toHaveURL(/\/profiles$/);
  const created = (await api.seen()).find((r) => r.method === 'POST' && r.url === '/api/profiles')!;
  expect(JSON.parse(created.body).data).toMatchObject({ organisationType: 'ngo', sectors: ['health'], locations: ['Musanze', 'Rubavu'], services: ['community health', 'training'] });

  await page.getByRole('button', { name: 'Add a personal profile' }).click();
  await page.getByLabel('Profile name').fill('Savings');
  await page.getByLabel('How long you can invest for').fill('1 to 3 years');
  await page.getByLabel('When you can go to events').fill('weekends');
  await page.getByLabel('Most you would spend on one event (FRW)').fill('50,000');
  await page.getByRole('button', { name: 'Add profile' }).click();
  await expect(page).toHaveURL(/\/profiles$/);
  const personal = (await api.seen()).filter((r) => r.method === 'POST' && r.url === '/api/profiles')[1]!;
  expect(JSON.parse(personal.body).data).toMatchObject({ horizon: '1 to 3 years', availability: 'weekends', budgetRwf: 50000 });

  // Edit keeps the answers.
  await page.getByRole('link', { name: 'Edit Health NGO' }).click();
  await expect(page.getByRole('group', { name: 'Type of organisation' }).getByRole('button', { name: 'NGO or non-profit' })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByLabel('Sectors you work in, separated by commas')).toHaveValue('health');

  // The rest of the flow works for this account: feed, save, shortlist, calendar, benchmarks.
  await open(page, '/');
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Amina');
  await page.getByRole('button', { name: /Save to shortlist/ }).first().click();
  await open(page, '/shortlist');
  await expect(page.getByRole('region', { name: 'Shortlist' })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Coming up' })).toBeVisible();
  await open(page, '/calendar');
  await expect(page.getByRole('region', { name: 'Coming up' })).toBeVisible();
  await open(page, '/benchmarks');
  await expect(page.getByRole('region', { name: 'Categories' })).toBeVisible();
});

test('stacked rows size to their content: Coming up and a category\'s awards', async ({ page }, testInfo) => {
  await stubSession(page, testInfo.testId);
  for (const size of [desktop, phone]) {
    await page.setViewportSize(size);
    for (const [route, list] of [
      ['/calendar', page.getByRole('region', { name: 'Coming up' }).getByRole('listitem')],
      ['/shortlist', page.getByRole('region', { name: 'Coming up' }).getByRole('listitem')],
      ['/benchmarks/freight', page.getByRole('main').getByRole('listitem')],
    ] as const) {
      await open(page, route);
      await expect(list.first()).toBeVisible();
      const rows = await list.evaluateAll((els) =>
        els.map((el) => ({
          height: el.getBoundingClientRect().height,
          children: [...el.children].reduce((n, c) => n + c.getBoundingClientRect().height, 0),
        })),
      );
      expect(rows.length).toBeGreaterThan(0);
      for (const r of rows) {
        expect(r.height, `${route}: a row is no taller than twice its content`).toBeLessThan(2 * r.children);
        expect(r.height, `${route}: a row is under 200px`).toBeLessThan(200);
      }
    }
  }
});
