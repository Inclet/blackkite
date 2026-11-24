import type { EventDates } from '../components/DeadlinePill/DeadlinePill';
import type { FeedRowProps } from '../components/FeedRow/FeedRow';
import type { FitLevel } from '../components/FitMeter/FitMeter';
import type { StateCardProps } from '../components/StateCard/StateCard';
import type { TrustState } from '../components/TrustNote/TrustNote';
import type { Stream } from '../lib/streams';

/** Content shown on the two styleguide boards. */
export interface StyleguideContent {
  /** Foundations "Urgency" pills: closing dates, read against now(). */
  urgencyDeadlines: string[];
  /** Foundations signature demo: the item that drops in. */
  droppedItem: string;
  feedRows: Omit<FeedRowProps, 'className'>[];
  fitLines: { level: FitLevel; reason: string }[];
  flags: string[];
  profileTag: string;
  fields: {
    amount: { label: string; value: string };
    trucks: { label: string; value: string; error: string };
    alerts: { label: string; description: string };
  };
  states: StateCardProps[];
}

/** One opportunity as the feed and detail screens see it (a per-user view of a catalogue row). */
export interface FeedItem {
  /** Route id: /o/:id. */
  id: string;
  stream: Stream;
  title: string;
  organisation: string;
  /** Short name used on the phone (e.g. NCST). Defaults to organisation. */
  organisationShort?: string;
  /** Fit word source; "not-scored" when the pair was not scored; null when fit is not shown (events, investments, closed). */
  fit: FitLevel | 'not-scored' | null;
  /** The top flag, shown in the row subtitle instead of the organisation (decision 24). */
  topFlag?: string;
  /** Events: topic and venue. */
  topic?: string;
  venue?: string;
  /** Investments: a short factual note (e.g. "trading on the RSE"). */
  note?: string;
  /** Closing date (YYYY-MM-DD), or null. Events use eventDates instead. */
  deadline: string | null;
  eventDates?: EventDates;
  /** Wording when there is no deadline. */
  noDeadlineText?: 'No deadline' | 'No deadline stated';
  /** Not shown in the phone list (decision 4: the phone board omits develoPPP). */
  hideOnPhone?: boolean;
  /** Arrived since the last visit: drops in once. */
  isNew?: boolean;
  detail: FeedItemDetail;
}

export interface FeedItemDetail {
  /** The profile it matched (e.g. Ironji-Trade). */
  profile?: string;
  location?: string;
  /** "why this matched" sentences, each quoting the requirement behind it. */
  reasons: string[];
  /** The "To check" note. */
  toCheck?: string;
  trust: {
    state: TrustState;
    /** The desktop pane's copy and the phone's shorter copy (the boards differ, C9). */
    desktop: string;
    phone: string;
  };
  /** Link to the original notice. */
  originalUrl: string;
}

/** The feed screens' data. */
export interface FeedContent {
  user: { name: string };
  /** "8 sources checked this morning". */
  sources: { checked: number; when: string };
  digest: { channel: string };
  items: FeedItem[];
}

/**
 * Shape of a fixture data set. The reference fixture reproduces the design
 * boards word for word; edge-cases adds the awkward rows from the Components board.
 */
export interface Fixture {
  /** Fixture name, as used in ?fixture=<name>. */
  name: string;
  styleguide: StyleguideContent;
  feed: FeedContent;
}
