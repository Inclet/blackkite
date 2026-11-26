/**
 * M4 member and admin routes (docs/api-contract.md section 5): calendar, the
 * personal calendar feed link, private manual items, share consent and the admin
 * publish step. Same client as every other route (cookies, JSON, ApiError).
 *
 * The contract names the routes and their inputs; where it leaves an answer's
 * shape open, the shapes below are the web track's reading, listed in the M4
 * report for the member-API track to confirm:
 * - feed-link and rotate answer `{url}`;
 * - POST/PATCH /api/items answer the item as GET /api/opportunities/{id} does;
 * - an owner's item carries `detail.ownItem` (what they entered, consent, visibility);
 * - GET /api/admin/catalogue?shareable=true lists private items whose owner consented.
 */
import { request } from './client';
import type { FitLevel } from '../components/FitMeter/FitMeter';
import type { Stream } from '../lib/streams';
import type { ItemState, OpportunityDetail } from './types';
import type { CatalogueItem } from './sources';

const enc = encodeURIComponent;

export type CalendarKind = 'deadlines' | 'events' | 'all';
export type CalendarEntryKind = 'deadline' | 'event_start' | 'event_end' | 'event';

/** One entry of GET /api/calendar. */
export interface CalendarEntry {
  id: string;
  stream: Stream;
  title: string;
  organisationShort?: string;
  kind: CalendarEntryKind;
  /** Kigali time of day, "HH:MM", when the source states one. */
  time?: string;
  fit?: FitLevel | 'not-scored' | null;
  state: ItemState;
  provisional: boolean;
}

export interface CalendarDay {
  /** YYYY-MM-DD, Kigali. */
  date: string;
  entries: CalendarEntry[];
}

export interface CalendarAnswer {
  days: CalendarDay[];
}

export interface CalendarQuery {
  from: string;
  to: string;
  kind: CalendarKind;
  saved: boolean;
}

/** GET /api/calendar/feed-link and POST …/rotate. */
export interface FeedLink {
  url: string;
}

export const CURRENCIES = ['RWF', 'USD', 'EUR'] as const;
export type Currency = (typeof CURRENCIES)[number];

/** POST /api/items (spec 6, private manual items). Absent keys were left empty. */
export interface PrivateItemInput {
  stream: Stream;
  title: string;
  organisation?: string | null;
  /** YYYY-MM-DD, Kigali. */
  deadline?: string | null;
  eventStart?: string | null;
  eventEnd?: string | null;
  value?: number | null;
  currency?: Currency | null;
  location?: string | null;
  /** http or https only. */
  url?: string | null;
  notes?: string | null;
}

/** On the owner's own manual items only (never on anyone else's view). */
export interface OwnItem {
  input: PrivateItemInput;
  /** The owner allows an admin to make it public. */
  shareConsent: boolean;
  /** "public" once an admin published it with consent (the owner stays for attribution). */
  visibility: 'private' | 'public';
}

export type OwnedDetail = OpportunityDetail & { detail: OpportunityDetail['detail'] & { ownItem?: OwnItem } };

/** A private item an admin may publish (GET /api/admin/catalogue?shareable=true). */
export type ShareableItem = CatalogueItem & { visibility?: 'private' | 'public'; shareConsent?: boolean };

export interface ShareablePage {
  total: number;
  items: ShareableItem[];
}

function query(params: Record<string, string | undefined>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v) q.set(k, v);
  const s = q.toString();
  return s ? `?${s}` : '';
}

export const m4Api = {
  calendar: ({ from, to, kind, saved }: CalendarQuery, signal?: AbortSignal) =>
    request<CalendarAnswer>(`/api/calendar${query({ from, to, kind, saved: saved ? 'true' : undefined })}`, { signal }),
  feedLink: (signal?: AbortSignal) => request<FeedLink>('/api/calendar/feed-link', { signal }),
  rotateFeedLink: () => request<FeedLink>('/api/calendar/feed-link/rotate', { method: 'POST' }),
  createItem: (item: PrivateItemInput) => request<OwnedDetail>('/api/items', { method: 'POST', body: item }),
  updateItem: (id: string, patch: Partial<PrivateItemInput>) => request<OwnedDetail>(`/api/items/${enc(id)}`, { method: 'PATCH', body: patch }),
  deleteItem: (id: string) => request<void>(`/api/items/${enc(id)}`, { method: 'DELETE' }),
  setShareConsent: (id: string, allow: boolean) => request<unknown>(`/api/items/${enc(id)}/share-consent`, { method: 'PUT', body: { allow } }),
  shareable: (signal?: AbortSignal) => request<ShareablePage>('/api/admin/catalogue?shareable=true', { signal }),
  publish: (id: string) => request<unknown>(`/api/admin/catalogue/${enc(id)}/publish`, { method: 'POST' }),
};
