/**
 * The admin source editor's form (spec 4.1 record, 4.2 config per collector type).
 * The config part is rendered from GET /api/admin/collector-types: one input per
 * field. Nested "object" fields are flattened to dotted names ("selectors.title"),
 * each a key inside its parent. Config keys the field list does not describe are
 * kept as they were.
 */
import type { FieldError } from '../../api/client';
import type { AdminSource, CollectorType, CollectorTypeInfo, ConfigField, SourceBody, SourceKind } from '../../api/sources';
import type { Stream } from '../../lib/streams';

export type FieldKind = 'text' | 'url' | 'integer' | 'number' | 'boolean' | 'choice' | 'list' | 'selector' | 'json';

/**
 * How a field kind (contract 4.1) is edited. object_list, map, json and anything
 * unknown are edited as JSON, so nothing is lost; an object with nested fields is
 * flattened first (flattenFields).
 */
export function fieldKind(kind: string): FieldKind {
  const t = kind.trim().toLowerCase();
  if (t === 'boolean' || t === 'bool') return 'boolean';
  if (t === 'integer' || t === 'int') return 'integer';
  if (t === 'number' || t === 'float') return 'number';
  if (t === 'url') return 'url';
  if (t === 'choice') return 'choice';
  if (t === 'string_list' || t === 'list') return 'list';
  if (t === 'selector') return 'selector';
  if (t === 'string' || t === 'str' || t === 'text') return 'text';
  return 'json';
}

/**
 * Nested object fields become dotted names. A nested field is required only when
 * every object above it is (an optional "detail" block stays optional).
 */
export function flattenFields(fields: ConfigField[], prefix = '', parentRequired = true): ConfigField[] {
  const out: ConfigField[] = [];
  for (const f of fields) {
    const name = prefix ? `${prefix}.${f.name}` : f.name;
    const required = f.required && parentRequired;
    if (f.kind === 'object' && f.fields && f.fields.length) out.push(...flattenFields(f.fields, name, required));
    else out.push({ ...f, name, required });
  }
  return out;
}

/** The hint under a config input: the API's help, the default and the range. */
export function fieldHint(f: ConfigField): string | undefined {
  const kind = fieldKind(f.kind);
  let help = f.help ?? '';
  if (kind === 'list') help = /one per line/i.test(help) ? help.replace(/,?\s*one per line/i, ', separated by commas') : [help, 'Separate with commas.'].filter(Boolean).join(' ');
  const parts = [help];
  if (kind === 'selector' && !/css selector/i.test(help)) parts.push('A CSS selector, or JSON such as {"css": "a", "attr": "href"}.');
  if (kind === 'json') parts.push('JSON.');
  const hasDefault = f.default !== null && f.default !== undefined && !(Array.isArray(f.default) && f.default.length === 0) && kind !== 'boolean';
  if (hasDefault) parts.push(`Default: ${Array.isArray(f.default) ? f.default.join(', ') : typeof f.default === 'object' ? JSON.stringify(f.default) : String(f.default)}.`);
  if ((kind === 'integer' || kind === 'number') && f.min !== null && f.min !== undefined && f.max !== null && f.max !== undefined) parts.push(`From ${f.min} to ${f.max}.`);
  return parts.filter(Boolean).join(' ') || undefined;
}

/** A switch's state: the value set in the form, else the API's default (so an "on" default is never turned off silently). */
export function switchOn(f: ConfigField, values: ConfigValues): boolean {
  const v = values[f.name];
  return typeof v === 'boolean' ? v : f.default === true;
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

export const RECORD_FIELDS = ['name', 'homeUrl', 'publisher', 'streams', 'kind', 'collectorType', 'schedule', 'rateLimit', 'accessNote'] as const;
export type RecordField = (typeof RECORD_FIELDS)[number];

export type FormErrors = Partial<Record<RecordField, string>> & {
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
  range: (min: number | null | undefined, max: number | null | undefined) =>
    min !== null && min !== undefined && max !== null && max !== undefined ? `Use a number from ${min} to ${max}.` : min !== null && min !== undefined ? `Use ${min} or more.` : `Use ${max} or less.`,
  choice: (options: string[]) => `Choose one of: ${options.join(', ')}.`,
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
  if (kind === 'json') return JSON.stringify(v);
  return typeof v === 'object' ? JSON.stringify(v) : String(v);
}

export function fieldsFor(types: CollectorTypeInfo[] | undefined, type: CollectorType | ''): ConfigField[] | null {
  if (!type || !types) return null;
  const info = types.find((t) => t.type === type);
  return info && info.fields.length ? flattenFields(info.fields) : null;
}

/** The form values for a config, given the type's fields (or the whole config as JSON). */
export function configValues(fields: ConfigField[] | null, config: Record<string, unknown>): ConfigValues {
  if (!fields) return { [WHOLE_CONFIG]: Object.keys(config).length ? JSON.stringify(config, null, 0) : '' };
  const out: ConfigValues = {};
  for (const f of fields) {
    const v = getPath(config, f.name);
    // A switch the config leaves unset shows (and saves) the API's default, so an "on" default is not turned off silently.
    out[f.name] = fieldKind(f.kind) === 'boolean' && v === undefined ? f.default === true : toText(fieldKind(f.kind), v);
  }
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
    const kind = fieldKind(f.kind);
    const raw = values[f.name];
    if (kind === 'boolean') {
      setPath(config, f.name, switchOn(f, values));
      continue;
    }
    const text = String(raw ?? '').trim();
    if (!text) {
      deletePath(config, f.name);
      if (f.required) errors[f.name] = FORM_COPY.required;
      continue;
    }
    const outOfRange = (n: number) => (f.min !== null && f.min !== undefined && n < f.min) || (f.max !== null && f.max !== undefined && n > f.max);
    if (kind === 'integer' || kind === 'number') {
      const n = Number(text);
      if (kind === 'integer' && !/^-?\d+$/.test(text)) errors[f.name] = FORM_COPY.integer;
      else if (!Number.isFinite(n)) errors[f.name] = FORM_COPY.number;
      else if (outOfRange(n)) errors[f.name] = FORM_COPY.range(f.min, f.max);
      else setPath(config, f.name, n);
    } else if (kind === 'choice') {
      if (f.options && f.options.length && !f.options.includes(text)) errors[f.name] = FORM_COPY.choice(f.options);
      else setPath(config, f.name, text);
    } else if (kind === 'selector') {
      if (text.startsWith('{')) {
        try {
          setPath(config, f.name, JSON.parse(text));
        } catch {
          errors[f.name] = FORM_COPY.json;
        }
      } else setPath(config, f.name, text);
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
      homeUrl: form.homeUrl.trim(),
      publisher: form.publisher.trim() || null,
      streams: form.streams,
      kind: form.kind,
      collectorType: form.collectorType,
      config: built.config,
      schedule: form.schedule.trim() || null,
      rateLimit,
      accessNote: form.accessNote.trim() || null,
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

/**
 * A server field message ("address 127.0.0.1 is not public", "is required") as a
 * sentence to show under its field: "Address 127.0.0.1 is not public.",
 * "This is required."
 */
export function fieldMessage(message: string): string {
  const t = message.trim().replace(/[.\s]+$/, '');
  if (!t) return '';
  if (/^(is|are|must|cannot|can't|has|have|needs|should|was)\b/i.test(t)) return `This ${t.charAt(0).toLowerCase()}${t.slice(1)}.`;
  return `${t.charAt(0).toUpperCase()}${t.slice(1)}.`;
}

/** "config.selectors.item" -> "Selectors: item"; "suggestionId" -> "Suggestion id". */
function pathLabel(path: string): string {
  const inner = path.startsWith('config.') ? path.slice('config.'.length) : path;
  const name = inner
    .split('.')
    .filter((p) => !/^\d+$/.test(p))
    .map((p) => p.replace(/([a-z])([A-Z])/g, '$1 $2').toLowerCase())
    .join('.');
  return fieldLabel({ name } as ConfigField);
}

/**
 * Place the API's field errors (contract 4.1 RefusalOut.errors) on the form:
 * record keys by name, `config.<path>` on the config input whose name is that
 * path or its longest prefix ("config.queries.0" on "queries"), or on the JSON
 * input when the type has no field list. The rest come back as sentences to
 * list under the form.
 */
export function placeServerErrors(errors: FieldError[], fields: ConfigField[] | null): { placed: FormErrors; unplaced: string[] } {
  const placed: FormErrors = {};
  const unplaced: string[] = [];
  const add = (current: string | undefined, text: string) => (current ? `${current} ${text}` : text);
  for (const e of errors) {
    const text = fieldMessage(e.message);
    if (!text) continue;
    const field = e.field;
    if (field && (RECORD_FIELDS as readonly string[]).includes(field)) {
      const key = field as RecordField;
      placed[key] = add(placed[key], text);
      continue;
    }
    if (field && (field === 'config' || field.startsWith('config.'))) {
      const path = field.slice('config.'.length);
      let target: string | null = null;
      if (!fields) target = WHOLE_CONFIG;
      else if (field !== 'config') {
        for (const f of fields) if ((path === f.name || path.startsWith(`${f.name}.`)) && (!target || f.name.length > target.length)) target = f.name;
      }
      if (target) {
        const config = (placed.config ??= {});
        config[target] = add(config[target], text);
        continue;
      }
    }
    const bare = e.message.trim().replace(/[.\s]+$/, '');
    unplaced.push(field ? `${pathLabel(field)}: ${bare}.` : text);
  }
  return { placed, unplaced };
}
