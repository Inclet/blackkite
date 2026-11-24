import type { FeedRowProps } from '../components/FeedRow/FeedRow';
import type { FitLevel } from '../components/FitMeter/FitMeter';
import type { StateCardProps } from '../components/StateCard/StateCard';

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

/**
 * Shape of a fixture data set. Filled in by ui-builder as screens are built;
 * the reference fixture reproduces the design boards word for word.
 */
export interface Fixture {
  /** Fixture name, as used in ?fixture=<name>. */
  name: string;
  styleguide: StyleguideContent;
}
