import type { Profile, ProfileCapacity, ProfileData, ProfileInput, ProfileType } from '../../api/types';
import { STREAMS, type Stream } from '../../lib/streams';

/** Spec 7.1: the owner's instrument list (personal profile). */
export const INSTRUMENTS = [
  'treasury bonds and bills',
  'RSE shares',
  'corporate bonds',
  'real estate and land',
  'private deals and startups',
] as const;

/** Spec 7.1: the owner's event topics (personal profile). */
export const EVENT_TOPICS = [
  'AI and tech',
  'logistics and trade',
  'startups and investors',
  'finance and fintech',
  'agriculture and food',
  'general networking',
] as const;

/** Streams a new profile starts with (spec 7.1: business profiles tender/funding/event, personal investment/event). */
export const DEFAULT_STREAMS: Record<ProfileType, Stream[]> = {
  business: ['tender', 'funding', 'event'],
  personal: ['investment', 'event'],
};

/** Everything as the inputs hold it: text for text fields, lists for chip groups. */
export interface ProfileForm {
  type: ProfileType;
  name: string;
  active: boolean;
  streams: Stream[];
  location: string;
  services: string;
  registrationsHeld: string;
  registrationsNotHeld: string;
  capacityModel: string;
  trucksInNetwork: string;
  refrigeratedInNetwork: string;
  ownedTrucks: string;
  /** Capacity tonnage as a range; equal ends (or a stored single figure) are one figure. */
  tonnageMin: string;
  tonnageMax: string;
  minContractRwf: string;
  provisional: boolean;
  instruments: string[];
  ticketMin: string;
  ticketMax: string;
  eventTopics: string[];
  excludeOrganisations: string;
  excludeSectors: string;
  excludeKeywords: string;
}

export type NumberField =
  | 'trucksInNetwork'
  | 'refrigeratedInNetwork'
  | 'ownedTrucks'
  | 'tonnageMin'
  | 'tonnageMax'
  | 'minContractRwf'
  | 'ticketMin'
  | 'ticketMax';
export type FormErrors = Partial<Record<'name' | 'streams' | NumberField, string>>;

export const ERRORS = {
  name: 'Give the profile a name, such as Ironji-Trade.',
  streams: 'Choose at least one stream.',
  /** The Components board's own wording for a number field. */
  number: 'Use a number, such as 100.',
  /** A count with decimals (the API takes whole trucks). */
  whole: 'Use a whole number, such as 100.',
  rwf: 'Use an amount in Rwandan francs, such as 5,000,000.',
  ticketOrder: 'Make this at least the smallest ticket.',
  tonnageOrder: 'Make this at least the smallest load.',
  /** The API takes a tonnage range in whole tonnes; one figure may have decimals. */
  tonnageWhole: 'Use whole tonnes for a range, such as 20.',
} as const;

/**
 * The data keys the API accepts for each type (api member/profiles.py
 * `BusinessData` / `PersonalData`; it refuses any other key with a 422).
 */
const COMMON_KEYS = ['streams', 'location', 'locations', 'exclusions', 'provisional'] as const;
export const DATA_KEYS: Record<ProfileType, readonly (keyof ProfileData)[]> = {
  business: [...COMMON_KEYS, 'services', 'sectors', 'capacity', 'registrationsHeld', 'registrationsNotHeld', 'minContractRwf'],
  personal: [...COMMON_KEYS, 'instruments', 'ticketRangeRwf', 'horizon', 'eventTopics', 'availability', 'budgetRwf'],
};
const CAPACITY_KEYS = ['model', 'trucksInNetwork', 'refrigeratedInNetwork', 'ownedTrucks', 'tonnage'] as const;

/** Only the keys of `data` valid for `type`: what survives a change of type. */
export function keysFor(type: ProfileType, data: Partial<ProfileData> | undefined): Partial<ProfileData> {
  const out: Partial<ProfileData> = {};
  if (!data) return out;
  for (const k of DATA_KEYS[type]) if (k in data) (out as Record<string, unknown>)[k] = data[k];
  return out;
}

const list = (v: string[] | null | undefined) => (v ?? []).join(', ');
const num = (v: number | null | undefined) => (v === null || v === undefined ? '' : String(v));

function tonnageEnd(t: ProfileCapacity['tonnage'], end: 'min' | 'max'): string {
  if (t === null || t === undefined) return '';
  return typeof t === 'number' ? String(t) : num(t[end]);
}

/** The two tonnage answers as the API takes them: null, one figure, or {min, max}. */
export function parseTonnage(minText: string, maxText: string): ProfileCapacity['tonnage'] {
  const lo = parseNumber(minText);
  const hi = parseNumber(maxText);
  if (lo === null && hi === null) return null;
  if (lo !== null && lo === hi) return lo;
  return { min: lo, max: hi };
}

export function toForm(profile: Pick<Profile, 'name' | 'type' | 'data' | 'active'> | null, type: ProfileType): ProfileForm {
  const d: Partial<ProfileData> = profile?.data ?? {};
  const t = profile?.type ?? type;
  return {
    type: t,
    name: profile?.name ?? '',
    active: profile?.active ?? true,
    streams: d.streams ?? (profile ? [] : DEFAULT_STREAMS[t]),
    location: d.location ?? '',
    services: list(d.services),
    registrationsHeld: list(d.registrationsHeld),
    registrationsNotHeld: list(d.registrationsNotHeld),
    capacityModel: d.capacity?.model ?? '',
    trucksInNetwork: num(d.capacity?.trucksInNetwork),
    refrigeratedInNetwork: num(d.capacity?.refrigeratedInNetwork),
    ownedTrucks: num(d.capacity?.ownedTrucks),
    tonnageMin: tonnageEnd(d.capacity?.tonnage, 'min'),
    tonnageMax: tonnageEnd(d.capacity?.tonnage, 'max'),
    minContractRwf: num(d.minContractRwf),
    provisional: d.provisional ?? false,
    instruments: d.instruments ?? [],
    ticketMin: num(d.ticketRangeRwf?.min),
    ticketMax: num(d.ticketRangeRwf?.max),
    eventTopics: d.eventTopics ?? [],
    excludeOrganisations: list(d.exclusions?.organisations),
    excludeSectors: list(d.exclusions?.sectors),
    excludeKeywords: list(d.exclusions?.keywords),
  };
}

/** "dry freight, cold chain" -> ["dry freight", "cold chain"]; empty -> null (not provided, never filters). */
export function parseList(s: string): string[] | null {
  const items = s
    .split(/[,\n]/)
    .map((x) => x.trim())
    .filter(Boolean);
  return items.length ? [...new Set(items)] : null;
}

/** "5,000,000" or "5 000 000" -> 5000000; "" -> null; anything else -> NaN. */
export function parseNumber(s: string): number | null {
  const t = s.trim().replace(/[\s,_]/g, '');
  if (t === '') return null;
  return /^\d+(\.\d+)?$/.test(t) ? Number(t) : NaN;
}

const BUSINESS_NUMBERS: NumberField[] = ['trucksInNetwork', 'refrigeratedInNetwork', 'ownedTrucks', 'tonnageMin', 'tonnageMax', 'minContractRwf'];
const PERSONAL_NUMBERS: NumberField[] = ['ticketMin', 'ticketMax'];

export function validate(f: ProfileForm): FormErrors {
  const e: FormErrors = {};
  if (!f.name.trim()) e.name = ERRORS.name;
  if (f.streams.length === 0) e.streams = ERRORS.streams;
  for (const k of f.type === 'business' ? BUSINESS_NUMBERS : PERSONAL_NUMBERS) {
    const n = parseNumber(f[k]);
    // Counts and francs are whole numbers in the API (it refuses 2.5 trucks); only tonnage takes decimals.
    const whole = !k.startsWith('tonnage');
    if (Number.isNaN(n) || (whole && n !== null && !Number.isInteger(n))) {
      e[k] = k === 'minContractRwf' || k.startsWith('ticket') ? ERRORS.rwf : Number.isNaN(n) ? ERRORS.number : ERRORS.whole;
    }
  }
  if (f.type === 'personal' && !e.ticketMin && !e.ticketMax) {
    const lo = parseNumber(f.ticketMin);
    const hi = parseNumber(f.ticketMax);
    if (lo !== null && hi !== null && hi < lo) e.ticketMax = ERRORS.ticketOrder;
  }
  if (f.type === 'business' && !e.tonnageMin && !e.tonnageMax) {
    const t = parseTonnage(f.tonnageMin, f.tonnageMax);
    if (t !== null && typeof t === 'object') {
      if (t.min != null && !Number.isInteger(t.min)) e.tonnageMin = ERRORS.tonnageWhole;
      if (t.max != null && !Number.isInteger(t.max)) e.tonnageMax = ERRORS.tonnageWhole;
      if (!e.tonnageMax && t.min != null && t.max != null && t.max < t.min) e.tonnageMax = ERRORS.tonnageOrder;
    }
  }
  return e;
}

/** The profile to send. Keys this form does not show are kept from `original`. */
export function toInput(f: ProfileForm, original?: Partial<ProfileData>): ProfileInput {
  // Only keys valid for the type being sent: after a change of type the old type's keys would be refused.
  const keep = keysFor(f.type, original);
  const keptCapacity: ProfileCapacity = {};
  for (const k of CAPACITY_KEYS) if (original?.capacity && k in original.capacity) (keptCapacity as Record<string, unknown>)[k] = original.capacity[k];
  const streams = STREAMS.filter((s) => f.streams.includes(s));
  const exclusions = {
    organisations: parseList(f.excludeOrganisations) ?? [],
    sectors: parseList(f.excludeSectors) ?? [],
    keywords: parseList(f.excludeKeywords) ?? [],
  };
  let data: ProfileData;
  if (f.type === 'business') {
    data = {
      ...keep,
      streams,
      location: f.location.trim() || null,
      services: parseList(f.services),
      registrationsHeld: parseList(f.registrationsHeld),
      registrationsNotHeld: parseList(f.registrationsNotHeld),
      capacity: {
        ...keptCapacity,
        model: f.capacityModel.trim() || null,
        trucksInNetwork: parseNumber(f.trucksInNetwork),
        refrigeratedInNetwork: parseNumber(f.refrigeratedInNetwork),
        ownedTrucks: parseNumber(f.ownedTrucks),
        tonnage: parseTonnage(f.tonnageMin, f.tonnageMax),
      },
      minContractRwf: parseNumber(f.minContractRwf),
      provisional: f.provisional,
      exclusions,
    };
  } else {
    data = {
      ...keep,
      streams,
      location: f.location.trim() || null,
      instruments: f.instruments.length ? f.instruments : null,
      ticketRangeRwf: { min: parseNumber(f.ticketMin), max: parseNumber(f.ticketMax) },
      eventTopics: f.eventTopics.length ? f.eventTopics : null,
      exclusions,
    };
  }
  return { name: f.name.trim(), type: f.type, active: f.active, data };
}

/** Options to show for a chip group: the spec's set, then anything else the profile already holds. */
export function chipOptions(base: readonly string[], selected: string[]): string[] {
  return [...base, ...selected.filter((s) => !base.includes(s))];
}
