/**
 * THE VISUAL CONTRACT.
 *
 * These values are fixed by the owner (KICKOFF_PROMPT.md, "The design contract:
 * pixel-level match") and must NEVER change: not the threshold, not the pass
 * mark, not a viewport, not a route. A page that cannot reach the pass mark is
 * reported to the owner; it is never made to pass by editing this file, masking
 * a region or touching a reference. CONTRACT.sha256 records this file's hash.
 */

/** pixelmatch per-pixel colour threshold. */
export const PIXELMATCH_THRESHOLD = 0.1;

/** Maximum share of differing pixels (of the viewport area) for a pass: 0.5 %. */
export const PASS_MAX_DIFF_RATIO = 0.005;

/** Required layout-shift sum, for both the reference and the built page. */
export const MAX_LAYOUT_SHIFT = 0;

/** The clock both pages see. Kigali, Tuesday afternoon. */
export const FROZEN_TIME = '2026-11-24T14:00:00+02:00';
export const TIMEZONE = 'Africa/Kigali';
export const LOCALE = 'en-GB';
export const DEVICE_SCALE_FACTOR = 1;

/** Pause between the two screenshots of the stability check. */
export const STABILITY_WAIT_MS = 500;

export interface VisualPage {
  /** Short name, used for spec and report file names. */
  name: string;
  /** File in design/reference/. */
  reference: string;
  viewport: { width: number; height: number };
  /** Built route, including the reference fixture switch. */
  route: string;
}

export const PAGES: readonly VisualPage[] = [
  { name: 'foundations', reference: 'foundations.html', viewport: { width: 1440, height: 1000 }, route: '/styleguide/foundations?fixture=reference' },
  { name: 'components', reference: 'components.html', viewport: { width: 1440, height: 1000 }, route: '/styleguide/components?fixture=reference' },
  { name: 'feed-desktop', reference: 'feed-desktop.html', viewport: { width: 1440, height: 900 }, route: '/?fixture=reference' },
  { name: 'feed-phone', reference: 'feed-phone.html', viewport: { width: 390, height: 844 }, route: '/?fixture=reference' },
  { name: 'opportunity-phone', reference: 'opportunity-phone.html', viewport: { width: 390, height: 844 }, route: '/o/wfp-logistics?fixture=reference' },
  { name: 'digest-email', reference: 'digest-email.html', viewport: { width: 640, height: 1000 }, route: '/digest/preview?fixture=reference' },
] as const;

export function pageByName(name: string): VisualPage {
  const page = PAGES.find((p) => p.name === name);
  if (!page) throw new Error(`No visual page named ${name}`);
  return page;
}
