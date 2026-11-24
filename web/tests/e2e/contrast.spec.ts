import { expect, test } from '@playwright/test';
import { colours, contrastRatio, open } from './helpers';

const checks: [string, { width: number; height: number }, string, string, number][] = [
  ['greeting summary (slate on mist)', { width: 1440, height: 900 }, '/?fixture=reference', 'main h1 + div', 4.5],
  ['row subtitle (slate on mist, selected row)', { width: 1440, height: 900 }, '/?fixture=reference', '[aria-current="true"] span span:nth-child(2)', 4.5],
  ['keyboard hint, 12px (slate on white)', { width: 1440, height: 900 }, '/?fixture=reference', 'text=J and K to move', 4.5],
  ['solid pill (white on graphite)', { width: 1440, height: 900 }, '/?fixture=reference', 'article >> text=6 days left', 4.5],
  ['tender tag (text on tint)', { width: 1440, height: 900 }, '/?fixture=reference', 'article >> text=Tender', 4.5],
  ['trust panel body (slate on stone)', { width: 390, height: 844 }, '/o/wfp-logistics?fixture=reference', 'text=Found on Job in Rwanda', 4.5],
  ['inactive tab (slate on white)', { width: 390, height: 844 }, '/?fixture=reference', 'nav >> text=Calendar', 4.5],
  ['closed row title (slate on white)', { width: 1440, height: 900 }, '/?fixture=edge-cases', 'text=Invitation for bids', 4.5],
  ['source down title (alert text on white)', { width: 1440, height: 900 }, '/?fixture=reference&state=source-down', 'text=We could not reach BNR today', 4.5],
];

for (const [name, size, route, selector, min] of checks) {
  test(`contrast: ${name} ≥ ${min}:1`, async ({ page }) => {
    await page.setViewportSize(size);
    await open(page, route);
    const { fg, bg } = await colours(page, selector);
    expect(contrastRatio(fg, bg)).toBeGreaterThanOrEqual(min);
  });
}
