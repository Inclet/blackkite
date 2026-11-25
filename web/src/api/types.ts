/**
 * Shapes of the member API (docs/api-contract.md section 2). Feed responses are
 * the web fixtures' own FeedContent / FeedItem, field for field.
 *
 * The contract fixes the feed and opportunity shapes; the profile, digest-settings
 * and account shapes below follow the schema (spec section 6, api models) in
 * camelCase and are listed in the Phase 4 report for the member-API track to confirm.
 */
import type { FeedContent, FeedItem, FeedItemDetail } from '../fixtures/types';
import type { Stream } from '../lib/streams';

export type { FeedContent, FeedItem };

/** user_opportunity.state (spec 6), per (user, opportunity) (decision 19). */
export type ItemState = 'unseen' | 'saved' | 'dismissed' | 'acting' | 'done';

/**
 * A feed item as the API sends it: always with the caller's state (contract
 * section 2, on feed, shortlist and detail items). The screens read saved,
 * acting and done from it.
 */
export type LiveFeedItem = FeedItem & { state: ItemState };

export interface ExtractedField {
  name: string;
  value: string;
  snippet?: string | null;
}

export interface OpportunitySource {
  name: string;
  url: string;
  isOriginal: boolean;
  firstSeen: string;
  lastSeen: string;
}

export interface OpportunityChange {
  field: string;
  old: string | null;
  new: string | null;
  at: string;
}

/** GET /opportunities/{id}: the FeedItem plus the detail extras. */
export type OpportunityDetail = LiveFeedItem & {
  detail: FeedItemDetail & {
    fields?: ExtractedField[];
    sources?: OpportunitySource[];
    documents?: string[];
    changes?: OpportunityChange[];
    note?: string | null;
  };
};

export interface StateUpdate {
  state: ItemState;
  dismissReason?: string;
}

export type ProfileType = 'business' | 'personal';

/** A range in whole units (the API's `Range`: integers, min not above max). */
export interface Range {
  min?: number | null;
  max?: number | null;
}

export interface ProfileCapacity {
  /** e.g. "partner network". */
  model?: string | null;
  trucksInNetwork?: number | null;
  refrigeratedInNetwork?: number | null;
  ownedTrucks?: number | null;
  /** Tonnes: one figure (any number from 0) or a range of whole tonnes (api `float | Range`). */
  tonnage?: number | Range | null;
}

export interface ProfileExclusions {
  organisations?: string[] | null;
  sectors?: string[] | null;
  keywords?: string[] | null;
}

/** Keys every profile type accepts (api member/profiles.py `_Common`). */
export interface CommonProfileData {
  /** Required by the API, at least one, no repeats. */
  streams: Stream[];
  location?: string | null;
  locations?: string[] | null;
  exclusions?: ProfileExclusions | null;
  /** A placeholder set the owner has yet to confirm (spec 7.1). */
  provisional?: boolean | null;
}

/** api `BusinessData`. */
export interface BusinessProfileData extends CommonProfileData {
  services?: string[] | null;
  sectors?: string[] | null;
  capacity?: ProfileCapacity | null;
  registrationsHeld?: string[] | null;
  registrationsNotHeld?: string[] | null;
  minContractRwf?: number | null;
}

/** api `PersonalData`. */
export interface PersonalProfileData extends CommonProfileData {
  instruments?: string[] | null;
  ticketRangeRwf?: Range | null;
  horizon?: string | null;
  eventTopics?: string[] | null;
  availability?: string | null;
  budgetRwf?: number | null;
}

/**
 * profile.data, camelCase (spec 7, 7.1). Null means "not provided yet" and never
 * hard-filters. The API refuses keys not valid for the profile's type (422), so
 * what is sent holds only BusinessProfileData or PersonalProfileData keys.
 */
export type ProfileData = BusinessProfileData & PersonalProfileData;

export interface Profile {
  id: string;
  name: string;
  type: ProfileType;
  data: ProfileData;
  version: number;
  active: boolean;
  /** ISO date-times. */
  createdAt?: string;
  updatedAt?: string;
}

export type ProfileInput = Pick<Profile, 'name' | 'type' | 'data'> & { active?: boolean };

/**
 * GET and PUT /api/digest-settings (api routes/digest_settings.py). No address:
 * the digest goes to the account's own email (GET /me), and PUT refuses unknown keys.
 */
export interface DigestSettings {
  channel: 'email';
  /** Decision 18: weekly on Monday, or off. */
  frequency: 'weekly' | 'off';
  day: 'mon';
  /** 0-100; null means no urgent alerts. */
  alertThreshold: number | null;
  /** Null means "the streams of my profiles". */
  streams: Stream[] | null;
}

/** GET /me (api routes/schemas.py UserOut; snake_case, as the API sends it). */
export interface Me {
  id: string;
  email: string;
  name: string | null;
  role: 'member' | 'admin';
  status?: string;
  created_at?: string;
}
