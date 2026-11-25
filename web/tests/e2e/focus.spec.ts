import { expect, test } from '@playwright/test';
import { open, stubSession } from './helpers';

// --bk-focus-ring: 0 0 0 2px #FFFFFF, 0 0 0 4px #2B2A28, as getComputedStyle serialises it.
const FOCUS_RING = 'rgb(255, 255, 255) 0px 0px 0px 2px, rgb(43, 42, 40) 0px 0px 0px 4px';

// The last number is the fewest Tab stops the page must have (the confirm and unsubscribe pages have one control).
for (const [name, size, route, minStops] of [
  ['desktop feed', { width: 1440, height: 900 }, '/?fixture=reference', 4],
  ['phone feed', { width: 390, height: 844 }, '/?fixture=reference', 4],
  ['phone opportunity', { width: 390, height: 844 }, '/o/wfp-logistics?fixture=reference', 4],
  ['sign-in confirm', { width: 390, height: 844 }, '/auth/confirm#token=abc', 1],
  ['unsubscribe', { width: 390, height: 844 }, '/unsubscribe#token=digest-abc', 1],
  ['unsubscribe, no token', { width: 1440, height: 900 }, '/unsubscribe', 1],
  ['live desktop feed', { width: 1440, height: 900 }, '/', 8],
  ['live phone opportunity', { width: 390, height: 844 }, '/o/wfp-logistics', 6],
  ['shortlist', { width: 1440, height: 900 }, '/shortlist', 5],
  ['profiles', { width: 390, height: 844 }, '/profiles', 5],
  ['business profile editor', { width: 1440, height: 900 }, '/profiles/p1', 12],
  ['personal profile editor', { width: 390, height: 844 }, '/profiles/new/personal', 12],
  ['digest settings', { width: 1440, height: 900 }, '/settings/digest', 8],
  ['account', { width: 390, height: 844 }, '/account', 5],
  ['more', { width: 390, height: 844 }, '/more', 5],
  ['sign-in', { width: 390, height: 844 }, '/sign-in', 2],
] as const) {
  test(`${name}: every Tab stop shows the double focus ring`, async ({ page }, testInfo) => {
    await stubSession(page, testInfo.testId);
    await page.setViewportSize(size);
    await open(page, route);
    await expect(page.getByText('This usually takes a moment.')).toHaveCount(0);
    const seen: string[] = [];
    for (let i = 0; i < 60; i++) {
      await page.keyboard.press('Tab');
      const label = await page.evaluate(() => {
        const el = document.activeElement as HTMLElement | null;
        if (!el || el === document.body) return null;
        // Inputs have no text: their name tells them apart.
        return `${el.tagName} ${(el.getAttribute('aria-label') ?? el.getAttribute('name') ?? el.textContent ?? '').trim().slice(0, 30)}`;
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
    expect(seen.length).toBeGreaterThanOrEqual(minStops);
  });
}
