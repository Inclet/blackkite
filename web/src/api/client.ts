/**
 * Typed client for the member API (docs/api-contract.md section 2).
 * Member routes live under /api (contract section 2); /me (GET) and /auth/* keep
 * their paths. Same origin (the dev and preview servers proxy these paths), cookies sent,
 * JSON in and out. Every failure is an ApiError with a kind the screens can word.
 */
import type {
  DigestSettings,
  DismissReason,
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
  /** 409: the request clashes with the current state (a name in use, a refused status change). */
  | 'conflict'
  | 'too-many'
  /** 5xx, an unexpected answer, or the network. Worded "We could not reach Blackkite just now". */
  | 'unreachable';

export class ApiError extends Error {
  constructor(
    readonly kind: ApiErrorKind,
    readonly status: number,
    /** The server's `detail`, when it sent one. Not shown as is; screens use their own wording. */
    readonly detail?: unknown,
    /** The whole JSON answer (admin refusals add `errors`, the promotion refusal `goodRuns` and `needed`). */
    readonly body?: unknown,
  ) {
    super(`${kind} (${status})`);
    this.name = 'ApiError';
  }
}

/** One refused field of an admin refusal (api FieldErrorOut). `field` is a dotted path, null when not about one field. */
export interface FieldError {
  field: string | null;
  message: string;
}

/** An admin refusal (api RefusalOut): the plain-sentence `detail` and the per-field `errors`. */
export interface Refusal {
  detail: string | null;
  errors: FieldError[];
}

/** The field errors in an answer, keeping only well-formed entries. */
export function fieldErrors(raw: unknown): FieldError[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((e): e is { field?: unknown; message: string } => e !== null && typeof e === 'object' && typeof (e as { message?: unknown }).message === 'string')
    .map((e) => ({ field: typeof e.field === 'string' && e.field ? e.field : null, message: e.message }));
}

/** The refusal an ApiError carries: `detail` when it is a string, and `errors` when sent. */
export function refusalOf(err: ApiError): Refusal {
  const body = err.body !== null && typeof err.body === 'object' ? (err.body as { errors?: unknown }) : {};
  return { detail: typeof err.detail === 'string' && err.detail.trim() ? err.detail.trim() : null, errors: fieldErrors(body.errors) };
}

function kindFor(status: number): ApiErrorKind {
  if (status === 401) return 'unauthorized';
  if (status === 403) return 'forbidden';
  if (status === 404) return 'not-found';
  if (status === 400 || status === 422) return 'invalid';
  if (status === 409) return 'conflict';
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
    let answer: unknown;
    try {
      answer = await res.json();
    } catch {
      answer = undefined;
    }
    const detail = answer !== null && typeof answer === 'object' ? (answer as { detail?: unknown }).detail : undefined;
    throw new ApiError(kindFor(res.status), res.status, detail, answer);
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
  /** open | closing_soon | expired (spec 6 status). */
  status?: string;
  /** Days ahead, Kigali calendar (7, 14, 30). */
  window?: string;
  /** strong | good | possible: that fit word or better. Never a number. */
  fit?: string;
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
    request<FeedContent & { items: LiveFeedItem[] }>(`/api/feed${query({ ...q })}`, { signal }),
  opportunity: (id: string, signal?: AbortSignal) => request<OpportunityDetail>(`/api/opportunities/${enc(id)}`, { signal }),
  setState: (id: string, state: ItemState, dismissReason?: DismissReason) =>
    request<unknown>(`/api/opportunities/${enc(id)}/state`, {
      method: 'PUT',
      body: (dismissReason ? { state, dismissReason } : { state }) satisfies StateUpdate,
    }),
  setNote: (id: string, note: string) => request<unknown>(`/api/opportunities/${enc(id)}/note`, { method: 'PUT', body: { note } }),
  shortlist: (signal?: AbortSignal) => request<LiveFeedItem[]>('/api/shortlist', { signal }),
  profiles: (signal?: AbortSignal) => request<Profile[]>('/api/profiles', { signal }),
  createProfile: (profile: ProfileInput) => request<Profile>('/api/profiles', { method: 'POST', body: profile }),
  updateProfile: (id: string, patch: Partial<ProfileInput>) => request<Profile>(`/api/profiles/${enc(id)}`, { method: 'PATCH', body: patch }),
  deleteProfile: (id: string) => request<void>(`/api/profiles/${enc(id)}`, { method: 'DELETE' }),
  digestSettings: (signal?: AbortSignal) => request<DigestSettings>('/api/digest-settings', { signal }),
  saveDigestSettings: (settings: DigestSettings) => request<DigestSettings>('/api/digest-settings', { method: 'PUT', body: settings }),
  me: (signal?: AbortSignal) => request<Me>('/me', { signal }),
  /** The account export, as JSON (spec 10: allow account export). */
  exportMe: () => request<unknown>('/api/me/export'),
  deleteMe: () => request<void>('/api/me', { method: 'DELETE' }),
  requestLink: (email: string) => request<unknown>('/auth/request-link', { method: 'POST', body: { email } }),
  logout: () => request<void>('/auth/logout', { method: 'POST' }),
};

export type Api = typeof api;
