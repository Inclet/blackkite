/**
 * M4 member and admin routes (docs/api-contract.md section 5, as built): calendar,
 * the personal calendar feed link, private manual items, share consent and the
 * admin publish step. Same client as every other route (cookies, JSON, ApiError).
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

/** GET /api/calendar/feed-link and POST …/rotate (api FeedLinkOut). 503 when the server has no calendar secret. */
export interface FeedLink {
  url: string;
  /** The same link with webcal://, which calendar apps open directly. */
  webcalUrl: string;
  /** Null: never stopped. */
  rotatedAt: string | null;
}

export const CURRENCIES = ['RWF', 'USD', 'EUR'] as const;
export type Currency = (typeof CURRENCIES)[number];

/** POST /api/items (api ItemIn; spec 6, private manual items). PATCH takes any of these; null clears (not stream or title). */
export interface PrivateItemInput {
  stream: Stream;
  title: string;
  organisation?: string | null;
  /** A date with an explicit year, Kigali: the form sends YYYY-MM-DD or YYYY-MM-DDTHH:MM (no zone). No time = end of day (start of day for eventStart). */
  deadline?: string | null;
  eventStart?: string | null;
  eventEnd?: string | null;
  value?: number | null;
  /** Three letters. */
  currency?: string | null;
  location?: string | null;
  /** http or https only. */
  url?: string | null;
  notes?: string | null;
}

/** `detail.ownItem` (api OwnItem): only on the caller's own manual item, private or published. */
export interface OwnItem {
  /** The owner allows an admin to make it public. */
  shareConsent: boolean;
  /** An admin made it public: consent can't be withdrawn and the owner can no longer edit or delete it (409). */
  published: boolean;
}

/** PUT /api/items/{id}/share-consent (api ShareConsentOut). */
export interface ShareConsent {
  allow: boolean;
  published: boolean;
}

export type OwnedDetail = OpportunityDetail & { detail: OpportunityDetail['detail'] & { ownItem?: OwnItem } };

/** A private item an admin may publish (GET /api/admin/catalogue?shareable=true): CatalogueItem with the M4 keys. */
export type ShareableItem = CatalogueItem & { visibility?: 'private' | 'public'; shareConsentAt?: string; madePublicAt?: string; url?: string };

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
  setShareConsent: (id: string, allow: boolean) => request<ShareConsent>(`/api/items/${enc(id)}/share-consent`, { method: 'PUT', body: { allow } }),
  shareable: (signal?: AbortSignal) => request<ShareablePage>('/api/admin/catalogue?shareable=true', { signal }),
  publish: (id: string) => request<ShareableItem>(`/api/admin/catalogue/${enc(id)}/publish`, { method: 'POST' }),
};
