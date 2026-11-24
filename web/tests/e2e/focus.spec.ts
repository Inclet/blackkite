import { expect, test } from '@playwright/test';
import { open } from './helpers';

// --bk-focus-ring: 0 0 0 2px #FFFFFF, 0 0 0 4px #2B2A28, as getComputedStyle serialises it.
const FOCUS_RING = 'rgb(255, 255, 255) 0px 0px 0px 2px, rgb(43, 42, 40) 0px 0px 0px 4px';

for (const [name, size, route] of [
  ['desktop feed', { width: 1440, height: 900 }, '/?fixture=reference'],
  ['phone feed', { width: 390, height: 844 }, '/?fixture=reference'],
  ['phone opportunity', { width: 390, height: 844 }, '/o/wfp-logistics?fixture=reference'],
] as const) {
  test(`${name}: every Tab stop shows the double focus ring`, async ({ page }) => {
    await page.setViewportSize(size);
    await open(page, route);
    const seen: string[] = [];
    for (let i = 0; i < 40; i++) {
      await page.keyboard.press('Tab');
      const label = await page.evaluate(() => {
        const el = document.activeElement as HTMLElement | null;
        if (!el || el === document.body) return null;
        return `${el.tagName} ${(el.getAttribute('aria-label') ?? el.textContent ?? '').trim().slice(0, 30)}`;
      });
      if (!label) break;
      if (seen.includes(label)) break;
      seen.push(label);
      // The reduced-motion rule leaves a 0.01ms transition on every property, so the first
      // computed value can still be the transparent start state. Poll until the transition
      // has settled; the settled value must be exactly the double ring.
      await expect
        .poll(
          () =>
            page.evaluate(() => {
              const el = document.activeElement as HTMLElement | null;
              return el ? getComputedStyle(el).boxShadow : 'no active element';
            }),
          { message: `focus ring on ${label}`, timeout: 1000 },
        )
        .toBe(FOCUS_RING);
    }
    expect(seen.length).toBeGreaterThanOrEqual(4);
  });
}
