import { expect, test } from '@playwright/test';
import { open } from './helpers';

test.use({ viewport: { width: 1440, height: 900 } });

test('with reduced motion nothing moves', async ({ page }) => {
  await open(page, '/?fixture=edge-cases&state=checking');
  const running = await page.evaluate(() => document.getAnimations().filter((a) => a.playState === 'running').length);
  expect(running).toBe(0);
});

test.describe('without reduced motion', () => {
  test.use({ reducedMotion: 'no-preference' });

  test('a new item drops in once, with the settle duration and easing', async ({ page }) => {
    await open(page, '/?fixture=edge-cases');
    const drops = await page.evaluate(() =>
      document
        .getAnimations()
        .filter((a) => (a as CSSAnimation).animationName?.includes('row-drop'))
        .map((a) => {
          const t = a.effect!.getTiming();
          const target = (a.effect as KeyframeEffect).target as Element;
          return { duration: t.duration, iterations: t.iterations, easing: getComputedStyle(target).animationTimingFunction };
        }),
    );
    expect(drops).toEqual([{ duration: 220, iterations: 1, easing: 'cubic-bezier(0.2, 0.8, 0.2, 1)' }]);
  });

  test('the feed kite circles on the --bk-orbit duration', async ({ page }) => {
    await open(page, '/?fixture=reference');
    const orbit = await page.evaluate(() =>
      document
        .getAnimations()
        .filter((a) => (a as CSSAnimation).animationName?.includes('orbit'))
        .map((a) => a.effect!.getTiming().duration),
    );
    expect(orbit).toEqual([8000]);
  });
});
