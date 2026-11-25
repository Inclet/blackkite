import type { IncomingMessage } from 'node:http';
import type { ProxyOptions } from 'vite';

/**
 * The API lives on its own origin in dev and preview; these exact paths go to it.
 * Everything else (including the /auth/confirm page) stays a web route, so the
 * visual harness's preview server works with no API running.
 */
export const API_PATHS = [
  '/auth/verify',
  '/auth/request-link',
  '/auth/logout',
  '/me',
  '/me/export',
  '/feed',
  '/digest-settings',
] as const;

/**
 * Paths that are both an API route and a web screen (/shortlist, /profiles,
 * /profiles/:id). A browser navigation (Accept: text/html) gets the app; the
 * client's fetches (Accept: application/json) go to the API.
 */
export const SHARED_PATHS = ['/shortlist', '/profiles'] as const;

/** True for a page load: the browser asks for HTML. The API client never does. */
export function wantsHtml(req: Pick<IncomingMessage, 'headers'>): boolean {
  return (req.headers.accept ?? '').includes('text/html');
}

/** Proxy keys (regexes matched against the request URL, query string included). */
export function apiProxy(target = process.env.BK_API_ORIGIN || 'http://127.0.0.1:8000'): Record<string, ProxyOptions> {
  const proxy: Record<string, ProxyOptions> = {};
  for (const path of API_PATHS) proxy[`^${path}(\\?.*)?$`] = { target };
  // /opportunities/{id}, /opportunities/{id}/state, /opportunities/{id}/note (no web screen lives here).
  proxy['^/opportunities/[^/?]+(/state|/note)?(\\?.*)?$'] = { target };
  // /shortlist; /profiles and /profiles/{id}: page loads stay in the app.
  const app = (req: IncomingMessage) => (wantsHtml(req) ? '/index.html' : undefined);
  proxy['^/shortlist(\\?.*)?$'] = { target, bypass: app };
  proxy['^/profiles(/[^/?]+)?(\\?.*)?$'] = { target, bypass: app };
  // /admin and anything under it (but not, say, /administrator).
  proxy['^/admin([/?].*)?$'] = { target };
  return proxy;
}
