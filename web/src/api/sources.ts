/**
 * Sources and admin API (docs/api-contract.md section 4; spec 3, 4.1 to 4.4).
 *
 * Paths: members under /api (/api/sources, /api/sources/{id}/mute,
 * /api/source-suggestions), admins under /api/admin. The Phase 3 source and admin
 * routes answer in snake_case (api routes/source_schemas.py, routes/schemas.py)
 * while the catalogue answers in camelCase; every answer goes through `camel()`
 * so the screens read one shape whichever the API sends. `config` and preview
 * `extra` are data, never renamed. Bodies are sent in snake_case, which the API
 * accepts in either case (its camelCase models also populate by name).
 */
import { request } from './client';
import type { Stream } from '../lib/streams';

export type Health = 'ok' | 'degraded' | 'failing' | 'unknown';
export type SourceKind = 'original' | 'publisher' | 'aggregator' | 'news' | 'community';
export type SourceStatus = 'suggested' | 'testing' | 'active' | 'paused' | 'retired';
export type CollectorType = 'rss' | 'html_list' | 'browser_list' | 'json_api' | 'search_query' | 'email_ingest' | 'custom';
export type SuggestionStatus = 'suggested' | 'accepted' | 'rejected';

export const SOURCE_KINDS: readonly SourceKind[] = ['original', 'publisher', 'aggregator', 'news', 'community'];
export const COLLECTOR_TYPES: readonly CollectorType[] = ['rss', 'html_list', 'browser_list', 'json_api', 'search_query', 'email_ingest', 'custom'];

/** GET /api/sources (api MemberSourceOut). */
export interface MemberSource {
  id: string;
  name: string;
  homeUrl: string;
  publisher: string | null;
  kind: SourceKind;
  streams: Stream[];
  lastSuccessAt: string | null;
  items30d: number;
  health: Health;
  muted: boolean;
}

/** GET /api/source-suggestions (api SuggestionOut); admins also get userId and reviewedBy. */
export interface Suggestion {
  id: string;
  url: string;
  note: string | null;
  status: SuggestionStatus;
  createdAt: string;
  reviewedAt: string | null;
  sourceId: string | null;
  userId?: string;
  reviewedBy?: string | null;
}

/** The admin view of a source (api SourceOut). */
export interface AdminSource {
  id: string;
  name: string;
  homeUrl: string;
  publisher: string | null;
  streams: Stream[];
  kind: SourceKind;
  collectorType: CollectorType;
  config: Record<string, unknown>;
  schedule: string | null;
  effectiveSchedule: string;
  rateLimit: number | null;
  accessNote: string | null;
  status: SourceStatus;
  addedBy: string | null;
  createdAt: string;
  updatedAt: string;
  configChangedAt: string | null;
  health: Health;
  lastSuccessAt: string | null;
  lastRunAt: string | null;
  items30d: number;
  /** Good runs since the last config change, toward the 2 needed for active. */
  promotionRuns: number;
}

/** POST /api/admin/sources and PATCH /api/admin/sources/{id} (api SourceIn / SourcePatch), snake_case. */
export interface SourceBody {
  name: string;
  home_url: string;
  publisher: string | null;
  streams: Stream[];
  kind: SourceKind;
  collector_type: CollectorType;
  config: Record<string, unknown>;
  schedule: string | null;
  rate_limit: number | null;
  access_note: string | null;
  /** Create only: the accepted suggestion this source comes from. */
  suggestion_id?: string;
}

/** POST /api/admin/sources/test-run (api PreviewIn). */
export interface PreviewBody {
  collector_type: CollectorType;
  config: Record<string, unknown>;
  home_url: string | null;
  streams: Stream[];
  rate_limit: number | null;
}

export interface SourceRun {
  id: string;
  startedAt: string;
  finishedAt: string | null;
  status: 'running' | 'succeeded' | 'failed';
  itemsFound: number;
  itemsNew: number;
  itemsFailed: number;
  error: string | null;
}

export interface PreviewItem {
  url: string;
  title: string;
  organisation: string | null;
  listedPublished: string | null;
  listedDeadline: string | null;
  snippet: string | null;
  detailUrl: string | null;
  extra: Record<string, string>;
}

export interface Preview {
  ok: boolean;
  error: string | null;
  items: PreviewItem[];
  totalParsed: number;
  requestsMade: number;
  elapsedSeconds: number;
}

/** One config field of a collector type (GET /api/admin/collector-types). */
export interface ConfigField {
  /** The config key; a dotted name ("selectors.title") is a nested key. */
  name: string;
  /** string | url | integer | number | boolean | list | object; anything else is edited as JSON. */
  type: string;
  required: boolean;
  help: string | null;
  label?: string | null;
}

export interface CollectorTypeInfo {
  type: CollectorType;
  label: string | null;
  fields: ConfigField[];
}

/** api routes/catalogue.py CatalogueItem (camelCase already). */
export interface CatalogueItem {
  id: string;
  stream: Stream;
  title: string;
  organisation: string | null;
  status: string;
  verification: string;
  trust: 'confirmed' | 'unconfirmed' | 'conflict';
  needsReview: boolean;
  reviewReasons: { code: string; detail: string }[];
  deadline: string | null;
  memberVisible: boolean;
  sources: { name: string; status: string; kind: string; isOriginal: boolean; url: string }[];
  createdAt: string;
  updatedAt: string;
}

export interface CataloguePage {
  total: number;
  items: CatalogueItem[];
}

/** api UserOut. */
export interface AdminUser {
  id: string;
  email: string;
  name: string | null;
  role: 'member' | 'admin';
  status: 'active' | 'deactivated';
  createdAt: string;
}

/** api InviteOut. */
export interface Invite {
  id: string;
  email: string;
  invitedBy: string | null;
  createdAt: string;
  expiresAt: string;
  acceptedAt: string | null;
  status: 'pending' | 'expired' | 'accepted';
}

/** Keys whose values are data (admin-entered config, collector extras): never renamed. */
const DATA_KEYS = new Set(['config', 'extra']);

const toCamel = (k: string) => k.replace(/_([a-z0-9])/g, (_, c: string) => c.toUpperCase());

/** snake_case keys to camelCase, deeply, leaving `config` and `extra` values as sent. */
export function camel<T>(value: unknown): T {
  if (Array.isArray(value)) return value.map((v) => camel(v)) as T;
  if (value === null || typeof value !== 'object') return value as T;
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
    const key = toCamel(k);
    out[key] = DATA_KEYS.has(key) ? v : camel(v);
  }
  return out as T;
}

/**
 * GET /api/admin/collector-types: a list of `{type, label?, fields}` (or a map
 * keyed by type). Field keys may be snake or camel case; `required` defaults to false.
 */
export function collectorTypesFrom(raw: unknown): CollectorTypeInfo[] {
  const entries: [string | undefined, Record<string, unknown>][] = Array.isArray(raw)
    ? raw.map((r) => [undefined, (r ?? {}) as Record<string, unknown>])
    : raw && typeof raw === 'object'
      ? Object.entries(raw as Record<string, unknown>).map(([k, v]) => [k, (Array.isArray(v) ? { fields: v } : v ?? {}) as Record<string, unknown>])
      : [];
  return entries
    .map(([key, r]) => {
      const c = camel<Record<string, unknown>>(r);
      const type = String(key ?? c.type ?? c.collectorType ?? c.name ?? '') as CollectorType;
      const fields = (Array.isArray(c.fields) ? c.fields : []).map((f) => {
        const o = (f ?? {}) as Record<string, unknown>;
        return {
          name: String(o.name ?? ''),
          type: String(o.type ?? 'string'),
          required: o.required === true,
          help: typeof o.help === 'string' && o.help ? o.help : null,
          label: typeof o.label === 'string' && o.label ? o.label : null,
        };
      });
      return { type, label: typeof c.label === 'string' && c.label ? c.label : null, fields: fields.filter((f) => f.name) };
    })
    .filter((t) => t.type);
}

const enc = encodeURIComponent;
const get = async <T>(path: string, signal?: AbortSignal) => camel<T>(await request<unknown>(path, { signal }));
const post = async <T>(path: string, body?: unknown) => camel<T>(await request<unknown>(path, { method: 'POST', body }));

export const sourcesApi = {
  // Members
  sources: (signal?: AbortSignal) => get<MemberSource[]>('/api/sources', signal),
  mute: (id: string) => request<void>(`/api/sources/${enc(id)}/mute`, { method: 'POST' }),
  unmute: (id: string) => request<void>(`/api/sources/${enc(id)}/mute`, { method: 'DELETE' }),
  mySuggestions: (signal?: AbortSignal) => get<Suggestion[]>('/api/source-suggestions', signal),
  suggest: (url: string, note: string | null) => post<Suggestion>('/api/source-suggestions', { url, note }),

  // Admins: sources
  adminSources: (signal?: AbortSignal) => get<AdminSource[]>('/api/admin/sources', signal),
  adminSource: (id: string, signal?: AbortSignal) => get<AdminSource>(`/api/admin/sources/${enc(id)}`, signal),
  createSource: (body: SourceBody) => post<AdminSource>('/api/admin/sources', body),
  updateSource: async (id: string, body: Partial<SourceBody>) =>
    camel<AdminSource>(await request<unknown>(`/api/admin/sources/${enc(id)}`, { method: 'PATCH', body })),
  setStatus: (id: string, status: SourceStatus) => post<AdminSource>(`/api/admin/sources/${enc(id)}/status`, { status }),
  runs: (id: string, signal?: AbortSignal) => get<SourceRun[]>(`/api/admin/sources/${enc(id)}/runs`, signal),
  /** Fetch once with the config on screen; the API writes nothing. */
  testRun: (body: PreviewBody) => post<Preview>('/api/admin/sources/test-run', body),
  collectorTypes: async (signal?: AbortSignal) => collectorTypesFrom(await request<unknown>('/api/admin/collector-types', { signal })),

  // Admins: suggestions
  adminSuggestions: (status: SuggestionStatus, signal?: AbortSignal) =>
    get<Suggestion[]>(`/api/admin/source-suggestions?status=${enc(status)}`, signal),
  acceptSuggestion: (id: string) => post<Suggestion>(`/api/admin/source-suggestions/${enc(id)}/accept`),
  rejectSuggestion: (id: string) => post<Suggestion>(`/api/admin/source-suggestions/${enc(id)}/reject`),

  // Admins: review queue
  reviewQueue: (signal?: AbortSignal) => get<CataloguePage>('/api/admin/catalogue?needsReview=true', signal),
  markReviewed: (id: string) => post<CatalogueItem>(`/api/admin/catalogue/${enc(id)}/review`),

  // Admins: users and invites
  users: (signal?: AbortSignal) => get<AdminUser[]>('/api/admin/users', signal),
  deactivate: (id: string) => post<AdminUser>(`/api/admin/users/${enc(id)}/deactivate`),
  invites: (signal?: AbortSignal) => get<Invite[]>('/api/admin/invites', signal),
  invite: (email: string) => post<Invite>('/api/admin/invites', { email }),
  withdrawInvite: (id: string) => request<void>(`/api/admin/invites/${enc(id)}`, { method: 'DELETE' }),
};
