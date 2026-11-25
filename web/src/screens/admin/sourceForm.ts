/**
 * The admin source editor's form (spec 4.1 record, 4.2 config per collector type).
 * The config part is rendered from GET /api/admin/collector-types: one input per
 * field, keyed by the field's name (a dotted name is a nested key). Config keys the
 * field list does not describe are kept as they were.
 */
import type { AdminSource, CollectorType, CollectorTypeInfo, ConfigField, SourceBody, SourceKind } from '../../api/sources';
import type { Stream } from '../../lib/streams';

export type FieldKind = 'text' | 'url' | 'integer' | 'number' | 'boolean' | 'list' | 'json';

/** How a field's declared type is edited. Unknown types are edited as JSON, so nothing is lost. */
export function fieldKind(type: string): FieldKind {
  const t = type.trim().toLowerCase();
  if (t === 'bool' || t === 'boolean') return 'boolean';
  if (t === 'int' || t === 'integer') return 'integer';
  if (t === 'number' || t === 'float' || t === 'decimal') return 'number';
  if (t === 'url' || t === 'uri') return 'url';
  if (t === 'list' || t === 'array' || t.startsWith('list[') || t.startsWith('list<') || t.endsWith('[]')) return 'list';
  if (t === 'object' || t === 'dict' || t === 'json' || t === 'mapping' || t.startsWith('dict[')) return 'json';
  if (t === 'string' || t === 'str' || t === 'text' || t === 'email' || t === 'selector' || t === 'regex' || t === 'pattern' || t === 'cron') return 'text';
  return 'json';
}

/** "selectors.item_title" -> "Selectors: item title". */
export function fieldLabel(f: ConfigField): string {
  if (f.label) return f.label;
  const parts = f.name.split('.').map((p) => p.replace(/_/g, ' '));
  const text = parts.join(': ');
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** The pseudo-field used when a type has no field list: the whole config as JSON. */
export const WHOLE_CONFIG = '__config';

export type ConfigValues = Record<string, string | boolean>;

export interface SourceForm {
  name: string;
  homeUrl: string;
  publisher: string;
  streams: Stream[];
  kind: SourceKind | '';
  collectorType: CollectorType | '';
  config: ConfigValues;
  schedule: string;
  rateLimit: string;
  accessNote: string;
}

export type FormErrors = Partial<Record<'name' | 'homeUrl' | 'streams' | 'kind' | 'collectorType' | 'schedule' | 'rateLimit', string>> & {
  config?: Record<string, string>;
};

export const FORM_COPY = {
  nameRequired: 'Give the source a name.',
  urlRequired: 'Enter the web address, such as https://www.umucyo.gov.rw.',
  urlInvalid: 'Use the full address, starting with https:// or http://.',
  streamsRequired: 'Choose at least one stream.',
  kindRequired: 'Choose what kind of source this is.',
  typeRequired: 'Choose how Blackkite collects from it.',
  originalSearch: 'Search results are never the issuer itself: choose another kind, or another collector.',
  schedule: 'Use five cron fields, such as 0 6 * * *.',
  rateLimit: 'Use seconds between requests, from 1 to 3600.',
  required: 'This is needed for this collector.',
  integer: 'Use a whole number, such as 20.',
  number: 'Use a number, such as 1.5.',
  json: 'Use JSON, such as {"css": "a.title"}.',
  configObject: 'Use a JSON object, such as {"feed_url": "https://…"}.',
} as const;

function getPath(obj: Record<string, unknown>, path: string): unknown {
  let cur: unknown = obj;
  for (const key of path.split('.')) {
    if (cur === null || typeof cur !== 'object' || Array.isArray(cur)) return undefined;
    cur = (cur as Record<string, unknown>)[key];
  }
  return cur;
}

function setPath(obj: Record<string, unknown>, path: string, value: unknown): void {
  const keys = path.split('.');
  let cur = obj;
  for (const key of keys.slice(0, -1)) {
    const next = cur[key];
    if (next === null || typeof next !== 'object' || Array.isArray(next)) cur[key] = {};
    cur = cur[key] as Record<string, unknown>;
  }
  cur[keys[keys.length - 1]!] = value;
}

function deletePath(obj: Record<string, unknown>, path: string): void {
  const keys = path.split('.');
  const parents: Record<string, unknown>[] = [obj];
  let cur: unknown = obj;
  for (const key of keys.slice(0, -1)) {
    cur = (cur as Record<string, unknown>)[key];
    if (cur === null || typeof cur !== 'object' || Array.isArray(cur)) return;
    parents.push(cur as Record<string, unknown>);
  }
  delete parents[parents.length - 1]![keys[keys.length - 1]!];
  // Drop objects the deletion left empty.
  for (let i = parents.length - 1; i > 0; i--) {
    if (Object.keys(parents[i]!).length) break;
    delete parents[i - 1]![keys[i - 1]!];
  }
}

/** A config value as the form shows it. */
function toText(kind: FieldKind, v: unknown): string | boolean {
  if (kind === 'boolean') return v === true;
  if (v === undefined || v === null) return '';
  if (kind === 'list') return Array.isArray(v) ? v.map(String).join(', ') : typeof v === 'string' ? v : JSON.stringify(v);
  if (kind === 'json') return typeof v === 'string' ? JSON.stringify(v) : JSON.stringify(v);
  return typeof v === 'object' ? JSON.stringify(v) : String(v);
}

export function fieldsFor(types: CollectorTypeInfo[] | undefined, type: CollectorType | ''): ConfigField[] | null {
  if (!type || !types) return null;
  const info = types.find((t) => t.type === type);
  return info && info.fields.length ? info.fields : null;
}

/** The form values for a config, given the type's fields (or the whole config as JSON). */
export function configValues(fields: ConfigField[] | null, config: Record<string, unknown>): ConfigValues {
  if (!fields) return { [WHOLE_CONFIG]: Object.keys(config).length ? JSON.stringify(config, null, 0) : '' };
  const out: ConfigValues = {};
  for (const f of fields) out[f.name] = toText(fieldKind(f.type), getPath(config, f.name));
  return out;
}

export function emptyForm(): SourceForm {
  return { name: '', homeUrl: '', publisher: '', streams: [], kind: '', collectorType: '', config: {}, schedule: '', rateLimit: '', accessNote: '' };
}

export function toForm(source: AdminSource, types: CollectorTypeInfo[] | undefined): SourceForm {
  return {
    name: source.name,
    homeUrl: source.homeUrl,
    publisher: source.publisher ?? '',
    streams: [...source.streams],
    kind: source.kind,
    collectorType: source.collectorType,
    config: configValues(fieldsFor(types, source.collectorType), source.config ?? {}),
    schedule: source.schedule ?? '',
    rateLimit: source.rateLimit === null || source.rateLimit === undefined ? '' : String(source.rateLimit),
    accessNote: source.accessNote ?? '',
  };
}

export function urlError(v: string): string | undefined {
  const t = v.trim();
  if (!t) return FORM_COPY.urlRequired;
  try {
    const u = new URL(t);
    if (u.protocol !== 'https:' && u.protocol !== 'http:') return FORM_COPY.urlInvalid;
  } catch {
    return FORM_COPY.urlInvalid;
  }
  return undefined;
}

/**
 * Build the config object from the form. `base` is the stored config (same
 * collector type only), so keys the field list does not describe survive.
 */
export function buildConfig(
  fields: ConfigField[] | null,
  values: ConfigValues,
  base: Record<string, unknown> = {},
): { config: Record<string, unknown>; errors: Record<string, string> } {
  const errors: Record<string, string> = {};
  if (!fields) {
    const text = String(values[WHOLE_CONFIG] ?? '').trim();
    if (!text) return { config: {}, errors };
    try {
      const parsed: unknown = JSON.parse(text);
      if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) errors[WHOLE_CONFIG] = FORM_COPY.configObject;
      else return { config: parsed as Record<string, unknown>, errors };
    } catch {
      errors[WHOLE_CONFIG] = FORM_COPY.configObject;
    }
    return { config: {}, errors };
  }
  const config = structuredClone(base);
  for (const f of fields) {
    const kind = fieldKind(f.type);
    const raw = values[f.name];
    if (kind === 'boolean') {
      setPath(config, f.name, raw === true);
      continue;
    }
    const text = String(raw ?? '').trim();
    if (!text) {
      deletePath(config, f.name);
      if (f.required) errors[f.name] = FORM_COPY.required;
      continue;
    }
    if (kind === 'integer') {
      if (!/^-?\d+$/.test(text)) errors[f.name] = FORM_COPY.integer;
      else setPath(config, f.name, Number(text));
    } else if (kind === 'number') {
      const n = Number(text);
      if (!Number.isFinite(n)) errors[f.name] = FORM_COPY.number;
      else setPath(config, f.name, n);
    } else if (kind === 'list') {
      const items = text
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
      if (!items.length && f.required) errors[f.name] = FORM_COPY.required;
      setPath(config, f.name, items);
    } else if (kind === 'json') {
      try {
        setPath(config, f.name, JSON.parse(text));
      } catch {
        errors[f.name] = FORM_COPY.json;
      }
    } else if (kind === 'url') {
      const bad = urlError(text);
      if (bad) errors[f.name] = bad;
      else setPath(config, f.name, text);
    } else {
      setPath(config, f.name, text);
    }
  }
  return { config, errors };
}

/** Check the record and config; returns the body to send when everything is fine. */
export function validate(
  form: SourceForm,
  fields: ConfigField[] | null,
  base: Record<string, unknown> | undefined,
): { errors: FormErrors; body: SourceBody | null } {
  const errors: FormErrors = {};
  if (!form.name.trim()) errors.name = FORM_COPY.nameRequired;
  const u = urlError(form.homeUrl);
  if (u) errors.homeUrl = u;
  if (!form.streams.length) errors.streams = FORM_COPY.streamsRequired;
  if (!form.kind) errors.kind = FORM_COPY.kindRequired;
  if (!form.collectorType) errors.collectorType = FORM_COPY.typeRequired;
  else if (form.kind === 'original' && form.collectorType === 'search_query') errors.kind = FORM_COPY.originalSearch;
  if (form.schedule.trim() && form.schedule.trim().split(/\s+/).length !== 5) errors.schedule = FORM_COPY.schedule;
  let rateLimit: number | null = null;
  if (form.rateLimit.trim()) {
    const n = Number(form.rateLimit.trim());
    if (!Number.isFinite(n) || n < 1 || n > 3600) errors.rateLimit = FORM_COPY.rateLimit;
    else rateLimit = n;
  }
  const built = buildConfig(fields, form.config, base);
  if (Object.keys(built.errors).length) errors.config = built.errors;
  if (Object.keys(errors).length || !form.kind || !form.collectorType) return { errors, body: null };
  return {
    errors,
    body: {
      name: form.name.trim(),
      home_url: form.homeUrl.trim(),
      publisher: form.publisher.trim() || null,
      streams: form.streams,
      kind: form.kind,
      collector_type: form.collectorType,
      config: built.config,
      schedule: form.schedule.trim() || null,
      rate_limit: rateLimit,
      access_note: form.accessNote.trim() || null,
    },
  };
}

/** Only the config part is checked for a test run (the record can still be half filled). */
export function validateForTest(
  form: SourceForm,
  fields: ConfigField[] | null,
  base: Record<string, unknown> | undefined,
): { errors: FormErrors; ok: boolean; config: Record<string, unknown> } {
  const errors: FormErrors = {};
  if (!form.collectorType) errors.collectorType = FORM_COPY.typeRequired;
  if (form.homeUrl.trim()) {
    const u = urlError(form.homeUrl);
    if (u) errors.homeUrl = u;
  }
  if (form.rateLimit.trim()) {
    const n = Number(form.rateLimit.trim());
    if (!Number.isFinite(n) || n < 1 || n > 3600) errors.rateLimit = FORM_COPY.rateLimit;
  }
  const built = buildConfig(fields, form.config, base);
  if (Object.keys(built.errors).length) errors.config = built.errors;
  return { errors, ok: Object.keys(errors).length === 0, config: built.config };
}

/** The API's `detail` as one readable line (FastAPI sends a string, or a list of {loc, msg}). */
export function detailText(detail: unknown): string | null {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const parts = detail
      .map((d) => {
        const o = (d ?? {}) as { loc?: unknown[]; msg?: unknown };
        const loc = Array.isArray(o.loc) ? o.loc.filter((x) => x !== 'body').join('.') : '';
        const msg = typeof o.msg === 'string' ? o.msg : '';
        return [loc, msg].filter(Boolean).join(': ');
      })
      .filter(Boolean);
    return parts.length ? parts.join('; ') : null;
  }
  return null;
}
