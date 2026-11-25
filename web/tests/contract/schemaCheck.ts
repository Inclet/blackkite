/**
 * A small JSON Schema checker for the subset Pydantic's model_json_schema()
 * writes: $ref into $defs, anyOf, enum, const, type, properties, required,
 * additionalProperties, items, min/max items and length, minimum/maximum and
 * format date-time. No dependency.
 *
 * Stricter than JSON Schema in two ways, to match what the API really sends:
 * - an object schema with `properties` and no `additionalProperties` refuses
 *   keys it does not list (the API never sends keys outside its model);
 * - a key the API drops when empty (`omitIfNone`, by model title) must be left
 *   out, not sent as null.
 * `format: uuid` is not checked: the stub's ids are short names (p1, u1).
 */

export interface Schema {
  $ref?: string;
  $defs?: Record<string, Schema>;
  anyOf?: Schema[];
  enum?: unknown[];
  const?: unknown;
  type?: string | string[];
  title?: string;
  properties?: Record<string, Schema>;
  required?: string[];
  additionalProperties?: boolean | Schema;
  items?: Schema;
  minItems?: number;
  maxItems?: number;
  minLength?: number;
  maxLength?: number;
  minimum?: number;
  maximum?: number;
  format?: string;
}

export interface CheckOptions {
  /** Model title -> keys the API omits rather than send as null. */
  omitIfNone?: Record<string, string[]>;
}

function typeOf(v: unknown): string {
  if (v === null) return 'null';
  if (Array.isArray(v)) return 'array';
  if (typeof v === 'number') return Number.isInteger(v) ? 'integer' : 'number';
  return typeof v;
}

function typeMatches(want: string, v: unknown): boolean {
  const got = typeOf(v);
  return want === got || (want === 'number' && got === 'integer');
}

const DATE_TIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})$/;

/** Every mismatch as "path: what", empty when the value fits the schema. */
export function check(value: unknown, root: Schema, options: CheckOptions = {}): string[] {
  const errors: string[] = [];
  const defs = root.$defs ?? {};

  const resolve = (s: Schema): Schema => {
    if (!s.$ref) return s;
    const name = s.$ref.replace('#/$defs/', '');
    const def = defs[name];
    if (!def) throw new Error(`unknown $ref ${s.$ref}`);
    return def;
  };

  const walk = (v: unknown, s0: Schema, path: string, out: string[]): void => {
    const s = resolve(s0);
    if (s.anyOf) {
      const tries = s.anyOf.map((alt) => {
        const e: string[] = [];
        walk(v, alt, path, e);
        return e;
      });
      if (tries.every((e) => e.length)) {
        const typeOnly = tries.map((e) => (e.length === 1 ? e[0]!.match(/^(.*): expected (.*), got (\w+)$/) : null));
        if (typeOnly.every((m) => m && m[1] === path)) {
          // Only the type was wrong for every alternative: one line naming them all.
          out.push(`${path}: expected ${typeOnly.map((m) => m![2]).join(' | ')}, got ${typeOf(v)}`);
        } else {
          // Report the closest alternative (fewest problems).
          out.push(...tries.reduce((a, b) => (b.length < a.length ? b : a)));
        }
      }
      return;
    }
    if (s.const !== undefined && v !== s.const) out.push(`${path}: expected ${JSON.stringify(s.const)}, got ${JSON.stringify(v)}`);
    if (s.enum && !s.enum.includes(v)) out.push(`${path}: ${JSON.stringify(v)} is not one of ${JSON.stringify(s.enum)}`);
    if (s.type !== undefined) {
      const types = Array.isArray(s.type) ? s.type : [s.type];
      if (!types.some((t) => typeMatches(t, v))) {
        out.push(`${path}: expected ${types.join(' | ')}, got ${typeOf(v)}`);
        return;
      }
    }
    if (typeof v === 'string') {
      if (s.minLength !== undefined && v.length < s.minLength) out.push(`${path}: shorter than ${s.minLength}`);
      if (s.maxLength !== undefined && v.length > s.maxLength) out.push(`${path}: longer than ${s.maxLength}`);
      if (s.format === 'date-time' && !DATE_TIME.test(v)) out.push(`${path}: ${JSON.stringify(v)} is not an ISO date-time`);
    }
    if (typeof v === 'number') {
      if (s.minimum !== undefined && v < s.minimum) out.push(`${path}: below ${s.minimum}`);
      if (s.maximum !== undefined && v > s.maximum) out.push(`${path}: above ${s.maximum}`);
    }
    if (Array.isArray(v)) {
      if (s.minItems !== undefined && v.length < s.minItems) out.push(`${path}: fewer than ${s.minItems} items`);
      if (s.maxItems !== undefined && v.length > s.maxItems) out.push(`${path}: more than ${s.maxItems} items`);
      if (s.items) v.forEach((x, i) => walk(x, s.items!, `${path}[${i}]`, out));
    }
    if (typeOf(v) === 'object' && (s.properties || s.additionalProperties !== undefined)) {
      const obj = v as Record<string, unknown>;
      const props = s.properties ?? {};
      for (const k of s.required ?? []) if (!(k in obj)) out.push(`${path}.${k}: missing (always sent by the API)`);
      const omitted = (s.title && options.omitIfNone?.[s.title]) || [];
      for (const [k, x] of Object.entries(obj)) {
        const p = props[k];
        if (p) {
          if (x === null && omitted.includes(k)) out.push(`${path}.${k}: the API leaves this out when empty, never null`);
          else walk(x, p, `${path}.${k}`, out);
        } else if (s.additionalProperties === undefined || s.additionalProperties === false) {
          out.push(`${path}.${k}: not in the API's ${s.title ?? 'model'}`);
        } else if (typeof s.additionalProperties === 'object') {
          walk(x, s.additionalProperties, `${path}.${k}`, out);
        }
      }
    }
  };

  walk(value, root, '$', errors);
  return errors;
}
