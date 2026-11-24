import crypto from 'node:crypto';
import { expect, request, test } from '@playwright/test';
import { fontBytes, googleCss, readManifest } from './fonts';

const sha256 = (data: Buffer | string) => crypto.createHash('sha256').update(data).digest('hex');
const gstaticUrls = (css: string) => [...new Set([...css.matchAll(/url\((https:\/\/fonts\.gstatic\.com\/[^)]+)\)/g)].map((m) => m[1]!))].sort();

test('vendored Figtree files match manifest.json', () => {
  const manifest = readManifest();
  expect(manifest.files.length).toBeGreaterThan(0);
  for (const f of manifest.files) {
    const bytes = fontBytes(f.file);
    expect(bytes.length, `${f.file} size`).toBe(f.bytes);
    expect(sha256(bytes), `${f.file} sha256`).toBe(f.sha256);
  }
  // The vendored CSS, with URLs put back, is byte for byte the response Google gave.
  const css = googleCss(manifest);
  expect(sha256(css), 'google-figtree.css (URLs restored) sha256').toBe(manifest.cssSha256);
  expect(gstaticUrls(css)).toEqual(manifest.files.map((f) => f.url).sort());
});

test('Google Fonts still serves the same Figtree bytes', async ({ browser }) => {
  const manifest = readManifest();
  // A current Chromium User-Agent: the one this browser sends, minus "Headless".
  const page = await browser.newPage();
  const userAgent = (await page.evaluate(() => navigator.userAgent)).replace('HeadlessChrome', 'Chrome');
  await page.close();

  const proxy = process.env.HTTPS_PROXY ?? process.env.https_proxy;
  const api = await request.newContext({ userAgent, ...(proxy ? { proxy: { server: proxy } } : {}) });
  try {
    let css: string;
    try {
      const res = await api.get(manifest.cssRequest, { timeout: 10_000 });
      if (!res.ok()) throw new Error(`HTTP ${res.status()}`);
      css = await res.text();
    } catch (err) {
      test.skip(true, `fonts.googleapis.com not reachable from here (${err instanceof Error ? err.message.split('\n')[0] : err}); only the offline hash check ran`);
      return;
    }
    expect(gstaticUrls(css), 'woff2 URLs Google serves now').toEqual(manifest.files.map((f) => f.url).sort());
    expect(sha256(css), 'Google css2 response sha256').toBe(manifest.cssSha256);
    for (const f of manifest.files) {
      const res = await api.get(f.url, { timeout: 10_000 });
      expect(res.ok(), `${f.url} status`).toBe(true);
      expect(sha256(await res.body()), `${f.file} sha256 from gstatic`).toBe(f.sha256);
    }
  } finally {
    await api.dispose();
  }
});
