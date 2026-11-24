import { expect, test } from '@playwright/test';
import { open } from './helpers';

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
      const stop = await page.evaluate(async () => {
        // The reduced-motion rule leaves a 0.01ms transition on every property: let it finish.
        await new Promise<void>((r) => requestAnimationFrame(() => requestAnimationFrame(() => r())));
        const el = document.activeElement as HTMLElement | null;
        if (!el || el === document.body) return null;
        return {
          label: `${el.tagName} ${(el.getAttribute('aria-label') ?? el.textContent ?? '').trim().slice(0, 30)}`,
          shadow: getComputedStyle(el).boxShadow,
        };
      });
      if (!stop) break;
      if (seen.includes(stop.label)) break;
      seen.push(stop.label);
      // --bk-focus-ring: 0 0 0 2px #FFFFFF, 0 0 0 4px #2B2A28
      expect(stop.shadow, `focus ring on ${stop.label}`).toContain('rgb(255, 255, 255) 0px 0px 0px 2px');
      expect(stop.shadow, `focus ring on ${stop.label}`).toContain('rgb(43, 42, 40) 0px 0px 0px 4px');
    }
    expect(seen.length).toBeGreaterThanOrEqual(4);
  });
}
