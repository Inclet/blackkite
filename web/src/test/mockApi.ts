import { vi } from 'vitest';
import { clearApiCache } from '../api/useResource';

export type Handler = (body: unknown, url: string) => unknown | Response | Promise<unknown | Response>;

export interface MockApi {
  fetch: ReturnType<typeof vi.fn>;
  /** Every call as "METHOD /path" with its parsed body. */
  calls: { key: string; body: unknown }[];
  /** Replace or add a route ("PUT /opportunities/x/state"). */
  on: (key: string, handler: Handler | unknown) => void;
}

export const status = (code: number, body: unknown = {}) => new Response(code === 204 ? null : JSON.stringify(body), { status: code });

/**
 * Stub fetch with a small route table keyed "METHOD /path" (query string ignored).
 * A handler's return value is sent as JSON 200, unless it is a Response. Unknown
 * routes answer 404. Clears the resource cache so each test starts cold.
 */
export function mockApi(routes: Record<string, Handler | unknown> = {}): MockApi {
  clearApiCache();
  const table = new Map(Object.entries(routes));
  const calls: MockApi['calls'] = [];
  const fetch = vi.fn(async (url: string, init: RequestInit = {}) => {
    const path = url.split('?')[0]!;
    const key = `${init.method ?? 'GET'} ${path}`;
    const body = typeof init.body === 'string' ? JSON.parse(init.body) : undefined;
    calls.push({ key, body });
    if (!table.has(key)) return status(404, { detail: 'Not found' });
    const h = table.get(key);
    const out = typeof h === 'function' ? await (h as Handler)(body, url) : h;
    if (out instanceof Response) return out;
    if (out === undefined) return status(204);
    return new Response(JSON.stringify(out), { status: 200, headers: { 'Content-Type': 'application/json' } });
  });
  vi.stubGlobal('fetch', fetch);
  return { fetch, calls, on: (key, handler) => void table.set(key, handler) };
}
