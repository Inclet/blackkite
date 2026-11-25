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
 * A feed item as the API may send it. `state` is not in the contract yet; when
 * present it is read, otherwise saved-ness comes from /shortlist membership.
 */
export type LiveFeedItem = FeedItem & { state?: ItemState };

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

export interface ProfileCapacity {
  /** e.g. "partner network". */
  model?: string | null;
  trucksInNetwork?: number | null;
  refrigeratedInNetwork?: number | null;
  ownedTrucks?: number | null;
  tonnage?: number | null;
}

export interface ProfileExclusions {
  organisations?: string[];
  sectors?: string[];
  keywords?: string[];
}

/** profile.data, camelCase (spec 7, 7.1). Null means "not provided yet" and never hard-filters. */
export interface ProfileData {
  streams?: Stream[];
  location?: string | null;
  /** Business. */
  services?: string[] | null;
  registrationsHeld?: string[] | null;
  registrationsNotHeld?: string[] | null;
  capacity?: ProfileCapacity | null;
  minContractRwf?: number | null;
  provisional?: boolean;
  /** Personal. */
  instruments?: string[] | null;
  ticketRangeRwf?: { min?: number | null; max?: number | null } | null;
  eventTopics?: string[] | null;
  exclusions?: ProfileExclusions | null;
}

export interface Profile {
  id: string;
  name: string;
  type: ProfileType;
  data: ProfileData;
  version: number;
  active: boolean;
}

export type ProfileInput = Pick<Profile, 'name' | 'type' | 'data'> & { active?: boolean };

export interface DigestSettings {
  channel: 'email';
  address?: string;
  /** Decision 18: weekly on Monday, or off. */
  frequency: 'weekly' | 'off';
  day: 'mon';
  /** 0-100; null means no urgent alerts. */
  alertThreshold: number | null;
  /** Null means "the streams of my profiles". */
  streams: Stream[] | null;
}

export interface Me {
  id: string;
  email: string;
  name: string | null;
  role: 'member' | 'admin';
}
