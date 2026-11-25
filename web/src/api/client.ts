/**
 * Typed client for the member API (docs/api-contract.md section 2).
 * Same origin (the dev and preview servers proxy these paths), cookies sent,
 * JSON in and out. Every failure is an ApiError with a kind the screens can word.
 */
import type {
  DigestSettings,
  FeedContent,
  ItemState,
  LiveFeedItem,
  Me,
  OpportunityDetail,
  Profile,
  ProfileInput,
  StateUpdate,
} from './types';

export type ApiErrorKind =
  /** 401: no session. The screens show the sign-in form. */
  | 'unauthorized'
  | 'forbidden'
  | 'not-found'
  /** 400 / 422: the server refused the input. */
  | 'invalid'
  | 'too-many'
  /** 5xx, an unexpected answer, or the network. Worded "We could not reach Blackkite just now". */
  | 'unreachable';

export class ApiError extends Error {
  constructor(
    readonly kind: ApiErrorKind,
    readonly status: number,
    /** The server's `detail`, when it sent one. Not shown as is; screens use their own wording. */
    readonly detail?: unknown,
  ) {
    super(`${kind} (${status})`);
    this.name = 'ApiError';
  }
}

function kindFor(status: number): ApiErrorKind {
  if (status === 401) return 'unauthorized';
  if (status === 403) return 'forbidden';
  if (status === 404) return 'not-found';
  if (status === 400 || status === 422) return 'invalid';
  if (status === 429) return 'too-many';
  return 'unreachable';
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  signal?: AbortSignal;
}

/** One request. Resolves with the parsed JSON (or undefined for an empty answer). */
export async function request<T>(path: string, { method = 'GET', body, signal }: RequestOptions = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      method,
      credentials: 'same-origin',
      headers: body === undefined ? { Accept: 'application/json' } : { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      // A redirect is never an API answer (it would be the sign-in page of something else).
      redirect: 'manual',
      signal,
    });
  } catch (e) {
    if ((e as { name?: unknown } | null)?.name === 'AbortError') throw e;
    throw new ApiError('unreachable', 0);
  }
  if (res.status < 200 || res.status >= 300) {
    let detail: unknown;
    try {
      detail = ((await res.json()) as { detail?: unknown } | null)?.detail;
    } catch {
      detail = undefined;
    }
    throw new ApiError(kindFor(res.status), res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  try {
    const text = await res.text();
    return (text === '' ? undefined : JSON.parse(text)) as T;
  } catch {
    throw new ApiError('unreachable', res.status);
  }
}

const enc = encodeURIComponent;

export interface FeedQuery {
  stream?: string;
  profile?: string;
  window?: string;
  verification?: string;
  source?: string;
  state?: string;
}

function query(params: Record<string, string | undefined>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v) q.set(k, v);
  const s = q.toString();
  return s ? `?${s}` : '';
}

export const api = {
  feed: (q: FeedQuery = {}, signal?: AbortSignal) =>
    request<FeedContent & { items: LiveFeedItem[] }>(`/feed${query({ ...q })}`, { signal }),
  opportunity: (id: string, signal?: AbortSignal) => request<OpportunityDetail>(`/opportunities/${enc(id)}`, { signal }),
  setState: (id: string, state: ItemState, dismissReason?: string) =>
    request<unknown>(`/opportunities/${enc(id)}/state`, {
      method: 'PUT',
      body: (dismissReason ? { state, dismissReason } : { state }) satisfies StateUpdate,
    }),
  setNote: (id: string, note: string) => request<unknown>(`/opportunities/${enc(id)}/note`, { method: 'PUT', body: { note } }),
  shortlist: (signal?: AbortSignal) => request<LiveFeedItem[]>('/shortlist', { signal }),
  profiles: (signal?: AbortSignal) => request<Profile[]>('/profiles', { signal }),
  createProfile: (profile: ProfileInput) => request<Profile>('/profiles', { method: 'POST', body: profile }),
  updateProfile: (id: string, patch: Partial<ProfileInput>) => request<Profile>(`/profiles/${enc(id)}`, { method: 'PATCH', body: patch }),
  deleteProfile: (id: string) => request<void>(`/profiles/${enc(id)}`, { method: 'DELETE' }),
  digestSettings: (signal?: AbortSignal) => request<DigestSettings>('/digest-settings', { signal }),
  saveDigestSettings: (settings: DigestSettings) => request<DigestSettings>('/digest-settings', { method: 'PUT', body: settings }),
  me: (signal?: AbortSignal) => request<Me>('/me', { signal }),
  /** The account export, as JSON (spec 10: allow account export). */
  exportMe: () => request<unknown>('/me/export'),
  deleteMe: () => request<void>('/me', { method: 'DELETE' }),
  requestLink: (email: string) => request<unknown>('/auth/request-link', { method: 'POST', body: { email } }),
  logout: () => request<void>('/auth/logout', { method: 'POST' }),
};

export type Api = typeof api;
