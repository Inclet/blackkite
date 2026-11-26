import { API_PATHS } from './apiProxy.ts';

/**
 * Web pages the edge server answers with their own headers (deploy/caddy/Caddyfile:
 * Referrer-Policy no-referrer). They must always come from the network, never as the
 * service worker's cached index.html, or they would carry that copy's headers.
 */
export const NETWORK_ONLY_PAGES = ['/auth/confirm', '/unsubscribe'] as const;

const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/**
 * Navigations the service worker must not answer with the SPA's index.html. Workbox
 * tests these against pathname + search. /api and everything under it (the calendar
 * feed, exports); the earlier API paths and the network-only pages, exactly (a query
 * string allowed), so /me stays an API path but /meetings would not.
 */
export const NAVIGATE_FALLBACK_DENYLIST: RegExp[] = [
  /^\/api(?:[/?]|$)/,
  ...[...API_PATHS, ...NETWORK_ONLY_PAGES].map((p) => new RegExp(`^${escape(p)}(?:\\?|$)`)),
];

/**
 * Workbox (generateSW) options: precache the app shell, SPA fallback for every other
 * navigation. Deliberately no `runtimeCaching`: the service worker never caches or
 * answers API requests, which always go to the network.
 */
export const workboxOptions = {
  navigateFallback: 'index.html',
  navigateFallbackDenylist: NAVIGATE_FALLBACK_DENYLIST,
};

/** Referrer-Policy per path, as the edge server sends it (deploy/caddy/Caddyfile); the preview server mirrors it. */
export function referrerPolicyFor(pathname: string): string {
  return (NETWORK_ONLY_PAGES as readonly string[]).includes(pathname) ? 'no-referrer' : 'strict-origin-when-cross-origin';
}
