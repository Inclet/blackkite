import { expect, test } from '@playwright/test';
import { colours, contrastRatio, open, stubSession } from './helpers';

const checks: [string, { width: number; height: number }, string, string, number][] = [
  ['greeting summary (slate on mist)', { width: 1440, height: 900 }, '/?fixture=reference', 'main h1 + div', 4.5],
  ['row subtitle (slate on mist, selected row)', { width: 1440, height: 900 }, '/?fixture=reference', '[aria-current="true"] span span:nth-child(2)', 4.5],
  ['keyboard hint, 12px (slate on white)', { width: 1440, height: 900 }, '/?fixture=reference', 'text=J and K to move', 4.5],
  ['solid pill (white on graphite)', { width: 1440, height: 900 }, '/?fixture=reference', 'article >> text=6 days left', 4.5],
  ['tender tag (text on tint)', { width: 1440, height: 900 }, '/?fixture=reference', 'article >> text=Tender', 4.5],
  ['trust panel body (slate on stone)', { width: 390, height: 844 }, '/o/wfp-logistics?fixture=reference', 'text=Found on Job in Rwanda', 4.5],
  ['inactive tab (slate on white)', { width: 390, height: 844 }, '/?fixture=reference', 'nav >> text=Calendar', 4.5],
  ['closed row title (slate on white)', { width: 1440, height: 900 }, '/?fixture=edge-cases', 'text=Invitation for bids', 4.5],
  ['sign-in confirm body (slate on mist)', { width: 390, height: 844 }, '/auth/confirm#token=abc', 'text=Press the button to finish', 4.5],
  ['sign-in confirm heading (graphite on mist)', { width: 1440, height: 900 }, '/auth/confirm#token=abc', 'h1', 4.5],
  ['unsubscribe body (slate on mist)', { width: 390, height: 844 }, '/unsubscribe#token=digest-abc', 'text=Press the button to stop', 4.5],
  ['unsubscribe heading (graphite on mist)', { width: 1440, height: 900 }, '/unsubscribe#token=digest-abc', 'h1', 4.5],
  ['unsubscribe settings link (graphite on mist)', { width: 390, height: 844 }, '/unsubscribe', 'text=Change your email settings', 4.5],
  ['source down title (alert text on white)', { width: 1440, height: 900 }, '/?fixture=reference&state=source-down', 'text=We could not reach BNR today', 4.5],
  ['sign-in body (slate on mist)', { width: 390, height: 844 }, '/sign-in', 'text=We email you a link', 4.5],
  ['shell summary (slate on mist)', { width: 1440, height: 900 }, '/profiles', 'text=Blackkite ranks every item', 4.5],
  ['profile row meta (slate on white)', { width: 1440, height: 900 }, '/profiles', 'text=Business · Tenders', 4.5],
  ['card label (slate on white)', { width: 390, height: 844 }, '/profiles/p1', 'text=Registrations >> nth=0', 4.5],
  ['switch description (slate on white)', { width: 1440, height: 900 }, '/settings/digest', 'text=Email me the day a strong fit', 4.5],
  ['unselected chip (graphite on white)', { width: 1440, height: 900 }, '/settings/digest', 'button:has-text("Tenders")', 4.5],
  ['selected all chip (white on graphite)', { width: 1440, height: 900 }, '/settings/digest', 'button:has-text("My profiles")', 4.5],
  ['account body (slate on white)', { width: 390, height: 844 }, '/account', 'text=Download everything', 4.5],
  ['live detail label (graphite on white)', { width: 1440, height: 900 }, '/', 'text=Your progress', 4.5],
  ['tab bar on a new screen (slate on white)', { width: 390, height: 844 }, '/more', 'nav[aria-label="Main"] >> text=Calendar', 4.5],
  ['source health tag (graphite on stone)', { width: 1440, height: 900 }, '/sources', 'text=Health: Working >> nth=0', 4.5],
  ['source meta (slate on white)', { width: 390, height: 844 }, '/sources', 'text=Job in Rwanda · Notice board · Tenders', 4.5],
  ['mute label (graphite on white)', { width: 1440, height: 900 }, '/sources', 'text=Mute >> nth=0', 4.5],
  ['field hint (slate on white)', { width: 1440, height: 900 }, '/admin/sources/new', 'text=Robots and terms position', 4.5],
  ['promotion gate (slate on white)', { width: 1440, height: 900 }, '/admin/sources/src-umucyo', 'text=Needs 2 good runs since the last config change: 1 so far. >> nth=0', 4.5],
  ['error log text (graphite on white)', { width: 390, height: 844 }, '/admin/sources/src-umucyo', 'text=HTTP 503 from www.umucyo.gov.rw', 4.5],
  ['review reason (graphite on white)', { width: 390, height: 844 }, '/admin/review', 'text=Job in Rwanda says 3 Dec 2026', 4.5],
  ['admin back link (graphite on mist)', { width: 1440, height: 900 }, '/admin/users', 'a:has-text("Admin") >> nth=1', 4.5],
];

for (const [name, size, route, selector, min] of checks) {
  test(`contrast: ${name} ≥ ${min}:1`, async ({ page }, testInfo) => {
    await stubSession(page, testInfo.testId);
    await page.setViewportSize(size);
    await open(page, route);
    await expect(page.getByText('This usually takes a moment.')).toHaveCount(0);
    const { fg, bg } = await colours(page, selector);
    expect(contrastRatio(fg, bg)).toBeGreaterThanOrEqual(min);
  });
}
