import type { Page } from '@playwright/test';
import { FROZEN_TIME } from '../visual/contract';
import { STUB_COOKIE, type Seed, type Seen } from './stubApi';

/** Open a route with the contract's frozen clock (Tuesday 24 Nov 2026, 14:00 Kigali). */
export async function open(page: Page, route: string): Promise<void> {
  await page.clock.setFixedTime(FROZEN_TIME);
  await page.goto(route);
  await page.evaluate(() => document.fonts.ready);
}

export interface Box {
  label: string;
  x: number;
  y: number;
  w: number;
  h: number;
  /** Height of the invisible ::after hit area, if any. */
  hitH: number;
  hitW: number;
}

/** Every visible interactive element with its box and its invisible hit area. */
export function interactiveBoxes(page: Page): Promise<Box[]> {
  return page.evaluate(() => {
    const els = [...document.querySelectorAll<HTMLElement>('a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])')];
    return els
      .filter((el) => {
        const r = el.getBoundingClientRect();
        const s = getComputedStyle(el);
        return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && !el.closest('[aria-hidden="true"]');
      })
      .map((el) => {
        const r = el.getBoundingClientRect();
        const after = getComputedStyle(el, '::after');
        const has = after.content !== 'none' && after.content !== 'normal' && after.position === 'absolute';
        return {
          label: `${el.tagName.toLowerCase()} "${(el.getAttribute('aria-label') ?? el.textContent ?? '').trim().slice(0, 40)}"`,
          x: r.x + scrollX,
          y: r.y + scrollY,
          w: r.width,
          h: r.height,
          hitH: has ? parseFloat(after.height) : 0,
          hitW: has ? parseFloat(after.width) : 0,
        };
      });
  });
}

function luminance([r, g, b]: number[]): number {
  const c = [r, g, b].map((v) => {
    const s = v! / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * c[0]! + 0.7152 * c[1]! + 0.0722 * c[2]!;
}

export function contrastRatio(a: number[], b: number[]): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi! + 0.05) / (lo! + 0.05);
}

/** Text colour and the first opaque background behind the element, as [r, g, b]. */
export function colours(page: Page, selector: string): Promise<{ fg: number[]; bg: number[] }> {
  return page.locator(selector).first().evaluate((el) => {
    const rgb = (s: string) => (s.match(/[\d.]+/g) ?? []).map(Number);
    const fg = rgb(getComputedStyle(el).color).slice(0, 3);
    let node: Element | null = el;
    while (node) {
      const c = rgb(getComputedStyle(node).backgroundColor);
      if (c.length === 3 || (c.length === 4 && c[3] === 1)) return { fg, bg: c.slice(0, 3) };
      node = node.parentElement;
    }
    return { fg, bg: [255, 255, 255] };
  });
}

/**
 * Give this test its own session on the stub API (stubApi.ts): sets the session
 * cookie and resets that session's data, optionally with overrides.
 */
export async function stubSession(page: Page, id: string, seed: Partial<Seed> = {}): Promise<{ seen: () => Promise<Seen[]> }> {
  const sid = id.replace(/[^\w-]/g, '_');
  const res = await fetch(`${stubOrigin()}/__stub/sessions/${sid}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(seed),
  });
  if (res.status !== 204) throw new Error(`stub session: ${res.status}`);
  await page.context().addCookies([{ name: STUB_COOKIE, value: sid, domain: '127.0.0.1', path: '/' }]);
  return { seen: async () => (await (await fetch(`${stubOrigin()}/__stub/sessions/${sid}/seen`)).json()) as Seen[] };
}

/** Requests the stub API saw with no session cookie. */
export async function anonymousSeen(): Promise<Seen[]> {
  return (await (await fetch(`${stubOrigin()}/__stub/anonymous/seen`)).json()) as Seen[];
}

function stubOrigin(): string {
  return `http://127.0.0.1:${process.env.BK_E2E_API_PORT}`;
}
