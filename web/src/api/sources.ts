/**
 * Sources and admin API (docs/api-contract.md section 4.1; spec 3, 4.1 to 4.4).
 *
 * Paths: members under /api (/api/sources, /api/sources/{id}/mute,
 * /api/source-suggestions), admins under /api/admin. JSON is camelCase both ways
 * (GET /me stays snake_case). Answers still go through `camel()`, a no-op on
 * camelCase, so an older snake_case answer reads the same. `config` and preview
 * `extra` are data: their keys are the collector's own (list_url…), never renamed.
 */
import { request, type FieldError } from './client';
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

/** GET/PATCH /api/admin/sources/{id} and status changes (api SourceDetailOut). */
export interface SourceDetail extends AdminSource {
  promotionGate: { goodRuns: number; needed: number; since: string | null; met: boolean };
  /** Newest first; oldStatus null = created. */
  statusHistory: { at: string; oldStatus: SourceStatus | null; newStatus: SourceStatus; changedBy: string | null; reason: string | null }[];
}

/** POST /api/admin/sources and PATCH /api/admin/sources/{id} (api SourceIn / SourcePatch). */
export interface SourceBody {
  name: string;
  homeUrl: string;
  publisher: string | null;
  streams: Stream[];
  kind: SourceKind;
  collectorType: CollectorType;
  config: Record<string, unknown>;
  schedule: string | null;
  rateLimit: number | null;
  accessNote: string | null;
  /** Create only: the accepted suggestion this source comes from. */
  suggestionId?: string;
}

/** POST /api/admin/sources/test-run (api PreviewIn). */
export interface PreviewBody {
  collectorType: CollectorType;
  config: Record<string, unknown>;
  homeUrl: string | null;
  streams: Stream[];
  rateLimit: number | null;
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
  /** What the run skipped without failing (decision 49); `[]` when none. Older answers leave it out: read as `[]`. */
  warnings: RunWarning[];
}

/** One thing a run (or a test run) skipped without failing (api RunWarningOut). */
export interface RunWarning {
  /** `email_no_link`: an email_ingest email with no usable link. Other kinds: show `message`. */
  kind: string;
  message: string;
  sender: string | null;
  subject: string | null;
  /** ISO 8601 when it parsed, else as written. */
  date: string | null;
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
  /** When the config itself was refused: one entry per field (api FieldErrorOut); otherwise empty. Older answers leave it out. */
  errors?: FieldError[];
  /** What the test run skipped without failing, same shape as a run's; `[]` when none. */
  warnings: RunWarning[];
  items: PreviewItem[];
  totalParsed: number;
  requestsMade: number;
  elapsedSeconds: number;
}

/** One config field of a collector type (GET /api/admin/collector-types, api ConfigFieldOut). */
export interface ConfigField {
  /** The key in `config` (inside its parent for nested fields). The editor flattens nesting to "selectors.title". */
  name: string;
  /**
   * string | url | integer | number | boolean | choice | string_list | selector |
   * object | object_list | map | json. Anything else is edited as JSON.
   */
  kind: string;
  required: boolean;
  help: string | null;
  default?: unknown;
  /** kind "choice". */
  options?: string[] | null;
  min?: number | null;
  max?: number | null;
  /** kinds "object" and "object_list". */
  fields?: ConfigField[] | null;
  label?: string | null;
}

export interface CollectorTypeInfo {
  type: CollectorType;
  label: string | null;
  /** False while the collector is not built yet: its runs fail cleanly. */
  implemented: boolean;
  /** "declared": the spec 4.2 fields, until the collector has its own config model. */
  schemaSource: 'model' | 'declared' | null;
  fields: ConfigField[];
}

/** GET /api/admin/sources/{id}/runs (api RunPage). */
export interface RunPage {
  total: number;
  items: SourceRun[];
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

/** api AdminUserOut. */
export interface AdminUser {
  id: string;
  email: string;
  name: string | null;
  role: 'member' | 'admin';
  status: 'active' | 'deactivated';
  createdAt: string;
  /** Null: never signed in. */
  lastSignInAt?: string | null;
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
      return {
        type,
        label: typeof c.label === 'string' && c.label ? c.label : null,
        implemented: c.implemented !== false,
        schemaSource: c.schemaSource === 'model' || c.schemaSource === 'declared' ? (c.schemaSource as 'model' | 'declared') : null,
        fields: configFieldsFrom(c.fields),
      };
    })
    .filter((t) => t.type);
}

function configFieldsFrom(raw: unknown): ConfigField[] {
  return (Array.isArray(raw) ? raw : [])
    .map((f) => {
      const o = (f ?? {}) as Record<string, unknown>;
      const num = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : null);
      const field: ConfigField = {
        name: String(o.name ?? ''),
        // `kind` (contract 4.1); `type` from earlier drafts.
        kind: String(o.kind ?? o.type ?? 'string'),
        required: o.required === true,
        help: typeof o.help === 'string' && o.help ? o.help : null,
        default: o.default ?? null,
        options: Array.isArray(o.options) ? o.options.map(String) : null,
        min: num(o.min),
        max: num(o.max),
        fields: Array.isArray(o.fields) ? configFieldsFrom(o.fields) : null,
        label: typeof o.label === 'string' && o.label ? o.label : null,
      };
      return field;
    })
    .filter((f) => f.name);
}

const enc = encodeURIComponent;
const get = async <T>(path: string, signal?: AbortSignal) => camel<T>(await request<unknown>(path, { signal }));
const post = async <T>(path: string, body?: unknown) => camel<T>(await request<unknown>(path, { method: 'POST', body }));

/** A RunPage, or a bare list of runs (earlier answers). */
function runPage(raw: unknown): RunPage {
  const page = camel<RunPage | SourceRun[]>(raw);
  const items = (Array.isArray(page) ? page : (page?.items ?? [])).map((r) => ({ ...r, warnings: Array.isArray(r.warnings) ? r.warnings : [] }));
  return { total: Array.isArray(page) ? page.length : (page?.total ?? 0), items };
}

export const sourcesApi = {
  // Members
  sources: (signal?: AbortSignal) => get<MemberSource[]>('/api/sources', signal),
  mute: (id: string) => request<void>(`/api/sources/${enc(id)}/mute`, { method: 'POST' }),
  unmute: (id: string) => request<void>(`/api/sources/${enc(id)}/mute`, { method: 'DELETE' }),
  mySuggestions: (signal?: AbortSignal) => get<Suggestion[]>('/api/source-suggestions', signal),
  suggest: (url: string, note: string | null) => post<Suggestion>('/api/source-suggestions', { url, note }),

  // Admins: sources
  adminSources: (signal?: AbortSignal) => get<AdminSource[]>('/api/admin/sources', signal),
  adminSource: (id: string, signal?: AbortSignal) => get<SourceDetail>(`/api/admin/sources/${enc(id)}`, signal),
  createSource: (body: SourceBody) => post<SourceDetail>('/api/admin/sources', body),
  updateSource: async (id: string, body: Partial<SourceBody>) =>
    camel<SourceDetail>(await request<unknown>(`/api/admin/sources/${enc(id)}`, { method: 'PATCH', body })),
  setStatus: (id: string, status: SourceStatus) => post<SourceDetail>(`/api/admin/sources/${enc(id)}/status`, { status }),
  /** The run history, newest first; `problems` gives the error log (failed runs and runs with warnings), `failed` failed runs only. */
  runs: async (id: string, opts: { failed?: boolean; problems?: boolean; limit?: number } = {}, signal?: AbortSignal) => {
    const q = new URLSearchParams();
    if (opts.failed) q.set('status', 'failed');
    if (opts.problems) q.set('problems', 'true');
    q.set('limit', String(opts.limit ?? 20));
    return runPage(await request<unknown>(`/api/admin/sources/${enc(id)}/runs?${q}`, { signal }));
  },
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
  setRole: async (id: string, role: AdminUser['role']) =>
    camel<AdminUser>(await request<unknown>(`/api/admin/users/${enc(id)}`, { method: 'PATCH', body: { role } })),
  invites: (signal?: AbortSignal) => get<Invite[]>('/api/admin/invites', signal),
  invite: (email: string) => post<Invite>('/api/admin/invites', { email }),
  withdrawInvite: (id: string) => request<void>(`/api/admin/invites/${enc(id)}`, { method: 'DELETE' }),
};
