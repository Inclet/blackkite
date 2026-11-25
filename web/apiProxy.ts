import type { ProxyOptions } from 'vite';

/**
 * The API lives on its own origin in dev and preview. Member routes are all under
 * /api (docs/api-contract.md section 2), so no API path is also a web page; the
 * earlier routes below keep their paths. Admin routes are under /api/admin (contract
 * section 4), so /admin/* is a web route: the admin screens. Everything else
 * (including the /auth/confirm and /unsubscribe pages, /shortlist, /profiles,
 * /sources and /admin/sources) stays a web route, so the visual harness's preview
 * server works with no API running.
 */
export const API_PATHS = ['/auth/verify', '/auth/request-link', '/auth/logout', '/me'] as const;

/** Proxy keys (regexes matched against the request URL, query string included). */
export function apiProxy(target = process.env.BK_API_ORIGIN || 'http://127.0.0.1:8000'): Record<string, ProxyOptions> {
  const proxy: Record<string, ProxyOptions> = {};
  // /api and anything under it (but not, say, /apiary).
  proxy['^/api([/?].*)?$'] = { target };
  for (const path of API_PATHS) proxy[`^${path}(\\?.*)?$`] = { target };
  return proxy;
}
