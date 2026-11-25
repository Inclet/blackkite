import { expect, test } from '@playwright/test';
import { interactiveBoxes, open, stubSession } from './helpers';

const WIDTHS = [360, 768, 1024, 1440, 1920];
const ROUTES = [
  '/?fixture=reference',
  '/o/wfp-logistics?fixture=reference',
  '/?fixture=edge-cases',
  '/?fixture=reference&state=checking',
  '/?fixture=reference&state=nothing-new',
  '/?fixture=reference&state=first-visit',
  '/?fixture=reference&state=source-down',
  '/auth/confirm#token=abc',
  // Live screens, against the stub API (a session per test).
  '/',
  '/o/wfp-logistics',
  '/shortlist',
  '/profiles',
  '/profiles/p1',
  '/profiles/p3',
  '/profiles/new/personal',
  '/settings/digest',
  '/account',
  '/more',
  '/sign-in',
];

/** Fewest interactive elements each page must have (the sign-in pages have one or two controls). */
const minBoxes = (route: string) => (route.startsWith('/auth/confirm') ? 1 : route === '/sign-in' ? 2 : 4);

for (const width of WIDTHS) {
  for (const route of ROUTES) {
    test(`${width}px ${route}: no sideways scroll, no overlaps, 44px targets`, async ({ page }, testInfo) => {
      await stubSession(page, testInfo.testId);
      await page.setViewportSize({ width, height: 900 });
      await open(page, route);
      // Live screens: wait until the data is on screen (the loading card has gone).
      await expect(page.getByText('This usually takes a moment.')).toHaveCount(0);

      const { scrollWidth, innerWidth } = await page.evaluate(() => ({
        scrollWidth: document.scrollingElement!.scrollWidth,
        innerWidth: window.innerWidth,
      }));
      expect(scrollWidth, 'no horizontal page scroll').toBeLessThanOrEqual(innerWidth);

      const boxes = await interactiveBoxes(page);
      expect(boxes.length).toBeGreaterThanOrEqual(minBoxes(route));
      for (const b of boxes) {
        // Where the board draws a control smaller, an invisible ::after layer must cover 44px (decision 2).
        expect(Math.max(b.h, b.hitH), `${b.label} is at least 44px tall`).toBeGreaterThanOrEqual(43.5);
        expect(Math.max(b.w, b.hitW), `${b.label} is at least 44px wide`).toBeGreaterThanOrEqual(43.5);
      }
      for (let i = 0; i < boxes.length; i++) {
        for (let j = i + 1; j < boxes.length; j++) {
          const a = boxes[i]!;
          const c = boxes[j]!;
          // A sticky bar overlaps content only while that content scrolls under it; in flow they never meet.
          if (a.floating !== c.floating) continue;
          const ox = Math.min(a.x + a.w, c.x + c.w) - Math.max(a.x, c.x);
          const oy = Math.min(a.y + a.h, c.y + c.h) - Math.max(a.y, c.y);
          expect(ox > 0.5 && oy > 0.5, `${a.label} overlaps ${c.label}`).toBe(false);
        }
      }
    });
  }
}
