import { expect, test } from '@playwright/test';
import { open } from './helpers';

test.use({ viewport: { width: 1440, height: 900 } });

const current = '[aria-label="Opportunities"] a[aria-current="true"]';

test('J/K move the selection and the URL without a reload; S saves; X removes', async ({ page }) => {
  await open(page, '/?fixture=reference');
  await page.evaluate(() => ((window as unknown as { __noReload: boolean }).__noReload = true));
  await expect(page.locator(current)).toContainText('Logistics, transport and warehousing support');

  await page.keyboard.press('j');
  await expect(page.locator(current)).toContainText('ABH Summit and Grand Finale');
  await expect(page).toHaveURL(/\/o\/abh-summit\?fixture=reference$/);
  await expect(page.getByRole('article').getByRole('heading', { level: 2 })).toHaveText('ABH Summit and Grand Finale');

  await page.keyboard.press('j');
  await page.keyboard.press('k');
  await expect(page.locator(current)).toContainText('ABH Summit');

  await page.keyboard.press('k');
  await page.keyboard.press('k'); // stops at the top
  await expect(page.locator(current)).toContainText('Logistics');
  await expect(page).toHaveURL(/\/o\/wfp-logistics\?fixture=reference$/);

  await page.keyboard.press('s');
  await expect(page.getByRole('button', { name: 'Save to shortlist' })).toHaveAttribute('aria-pressed', 'true');

  await page.keyboard.press('x');
  await expect(page.locator('[aria-label="Opportunities"] a')).toHaveCount(5);
  await expect(page.locator(current)).toContainText('ABH Summit');
  await expect(page).toHaveURL(/\/o\/abh-summit/);

  expect(await page.evaluate(() => (window as unknown as { __noReload?: boolean }).__noReload)).toBe(true);
});

test('keys are ignored with a modifier held', async ({ page }) => {
  await open(page, '/?fixture=reference');
  await page.keyboard.press('Control+j');
  await page.keyboard.press('Alt+x');
  await page.keyboard.press('Shift+X');
  await expect(page.locator(current)).toContainText('Logistics');
  await expect(page.locator('[aria-label="Opportunities"] a')).toHaveCount(6);
});

test('the phone layout starts below 792px', async ({ page }) => {
  await page.setViewportSize({ width: 791, height: 900 });
  await open(page, '/?fixture=reference');
  await expect(page.getByRole('button', { name: 'Your account' })).toBeVisible();
  await page.setViewportSize({ width: 792, height: 900 });
  await expect(page.getByRole('article')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Your account' })).toHaveCount(0);
});
