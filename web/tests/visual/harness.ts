import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { expect, test, type BrowserContext, type Page } from '@playwright/test';
import pixelmatch from 'pixelmatch';
import { PNG } from 'pngjs';
import {
  DEVICE_SCALE_FACTOR,
  FROZEN_TIME,
  MAX_LAYOUT_SHIFT,
  PASS_MAX_DIFF_RATIO,
  PIXELMATCH_THRESHOLD,
  STABILITY_WAIT_MS,
  pageByName,
  type VisualPage,
} from './contract';
import { fontBytes, googleCss, readManifest } from './fonts';
import { referenceDir, reportsDir, resultsDir } from './paths';

export interface Capture {
  url: string;
  layoutShift: number;
  stable: boolean;
  /** Figtree faces with status "loaded" when the screenshot was taken. */
  figtreeLoaded: number;
  /** External requests the harness refused (should be none). */
  blocked: string[];
}

export interface PageResult {
  page: string;
  viewport: string;
  diffPixels: number | null;
  totalPixels: number;
  diffRatio: number | null;
  pass: boolean;
  reference: Capture | null;
  built: Capture | null;
  error?: string;
}

declare global {
  interface Window {
    __bkLayoutShift: number;
  }
}

/** Serve the vendored Google Fonts bytes for every font request; refuse any other external request. */
async function routeOffline(context: BrowserContext, blocked: string[]): Promise<void> {
  const manifest = readManifest();
  const css = googleCss(manifest);
  // Routes are matched last-registered first: the catch-all goes in first.
  await context.route(/^https?:\/\/(?!127\.0\.0\.1[:/]|localhost[:/])/, (route) => {
    blocked.push(route.request().url());
    return route.abort('blockedbyclient');
  });
  await context.route('https://fonts.googleapis.com/css2*', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'text/css; charset=utf-8',
      headers: { 'access-control-allow-origin': '*' },
      body: css,
    }),
  );
  await context.route('https://fonts.gstatic.com/**', (route) => {
    const file = new URL(route.request().url()).pathname.split('/').pop() ?? '';
    const entry = manifest.files.find((f) => f.file === file);
    if (!entry) {
      blocked.push(route.request().url());
      return route.fulfill({ status: 404, body: '' });
    }
    return route.fulfill({
      status: 200,
      contentType: 'font/woff2',
      headers: { 'access-control-allow-origin': '*' },
      body: fontBytes(file),
    });
  });
}

async function settle(page: Page): Promise<void> {
  await page.evaluate(async () => {
    const frames = () => new Promise<void>((r) => requestAnimationFrame(() => requestAnimationFrame(() => r())));
    for (let i = 0; i < 20; i++) {
      await document.fonts.ready;
      await frames();
      if (document.fonts.status === 'loaded') return;
    }
  });
}

async function capture(page: Page, url: string, vp: VisualPage, blocked: string[]): Promise<{ shot: Buffer; capture: Capture }> {
  await page.clock.setFixedTime(FROZEN_TIME);
  await page.goto(url, { waitUntil: 'load' });
  await settle(page);

  const env = await page.evaluate(() => ({
    dpr: window.devicePixelRatio,
    reduced: matchMedia('(prefers-reduced-motion: reduce)').matches,
    width: window.innerWidth,
    height: window.innerHeight,
  }));
  expect(env, 'browser environment must match the contract').toEqual({
    dpr: DEVICE_SCALE_FACTOR,
    reduced: true,
    width: vp.viewport.width,
    height: vp.viewport.height,
  });

  const first = await page.screenshot({ fullPage: false });
  await page.waitForTimeout(STABILITY_WAIT_MS);
  const second = await page.screenshot({ fullPage: false });

  const { layoutShift, figtreeLoaded } = await page.evaluate(() => ({
    layoutShift: window.__bkLayoutShift,
    figtreeLoaded: [...document.fonts].filter((f) => f.family.replace(/["']/g, '') === 'Figtree' && f.status === 'loaded').length,
  }));

  return {
    shot: first,
    capture: { url, layoutShift, stable: first.equals(second), figtreeLoaded, blocked: [...blocked] },
  };
}

function writeResult(result: PageResult): void {
  fs.mkdirSync(resultsDir, { recursive: true });
  fs.writeFileSync(path.join(resultsDir, `${result.page}.json`), JSON.stringify(result, null, 2));
}

/** One visual test: reference vs built, for one row of the contract. */
export function visualTest(name: string): void {
  const vp = pageByName(name);
  test.use({ viewport: vp.viewport });

  test(`${vp.name} ${vp.viewport.width}x${vp.viewport.height} matches ${vp.reference}`, async ({ context, baseURL }) => {
    test.setTimeout(60_000);
    const totalPixels = vp.viewport.width * vp.viewport.height;
    const result: PageResult = {
      page: vp.name,
      viewport: `${vp.viewport.width}x${vp.viewport.height}`,
      diffPixels: null,
      totalPixels,
      diffRatio: null,
      pass: false,
      reference: null,
      built: null,
    };
    try {
      const blocked: string[] = [];
      await routeOffline(context, blocked);
      await context.addInitScript(() => {
        window.__bkLayoutShift = 0;
        new PerformanceObserver((list) => {
          for (const entry of list.getEntries() as (PerformanceEntry & { value: number; hadRecentInput: boolean })[]) {
            if (!entry.hadRecentInput) window.__bkLayoutShift += entry.value;
          }
        }).observe({ type: 'layout-shift', buffered: true });
      });

      const refUrl = pathToFileURL(path.join(referenceDir, vp.reference)).href;
      const refPage = await context.newPage();
      const ref = await capture(refPage, refUrl, vp, blocked);
      result.reference = ref.capture;
      blocked.length = 0;

      const builtPage = await context.newPage();
      const built = await capture(builtPage, new URL(vp.route, baseURL).href, vp, blocked);
      result.built = built.capture;

      const a = PNG.sync.read(ref.shot);
      const b = PNG.sync.read(built.shot);
      const { width, height } = vp.viewport;
      const diff = new PNG({ width, height });
      const diffPixels = pixelmatch(a.data, b.data, diff.data, width, height, { threshold: PIXELMATCH_THRESHOLD });

      fs.mkdirSync(reportsDir, { recursive: true });
      fs.writeFileSync(path.join(reportsDir, `${vp.name}-reference.png`), ref.shot);
      fs.writeFileSync(path.join(reportsDir, `${vp.name}-built.png`), built.shot);
      fs.writeFileSync(path.join(reportsDir, `${vp.name}-diff.png`), PNG.sync.write(diff));

      result.diffPixels = diffPixels;
      result.diffRatio = diffPixels / totalPixels;
      result.pass =
        result.diffRatio <= PASS_MAX_DIFF_RATIO &&
        // Owner ruling 2026-11-24 (docs/decisions.md #16): only the built page's layout
        // shift decides pass/fail. The reference's own font-swap shift is reported, not judged.
        built.capture.layoutShift <= MAX_LAYOUT_SHIFT &&
        ref.capture.stable &&
        built.capture.stable;
    } catch (err) {
      result.error = err instanceof Error ? err.message : String(err);
      throw err;
    } finally {
      writeResult(result);
    }

    const pct = ((result.diffRatio ?? 1) * 100).toFixed(2);
    expect.soft(result.reference?.stable, 'reference screenshots 500 ms apart must be identical').toBe(true);
    expect.soft(result.built?.stable, 'built screenshots 500 ms apart must be identical').toBe(true);
    expect.soft(result.built?.layoutShift, 'built layout-shift sum').toBe(MAX_LAYOUT_SHIFT);
    expect(result.diffRatio!, `${vp.name}: ${pct}% of pixels differ (pass mark ${PASS_MAX_DIFF_RATIO * 100}%)`).toBeLessThanOrEqual(
      PASS_MAX_DIFF_RATIO,
    );
  });
}
