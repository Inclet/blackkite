import { cx } from '../../lib/streams';
import { daysLeft, deadlineLabel, deadlineWeight, eventEnded, eventLabel, eventWeight, formatShortDate } from '../../lib/deadline';
import styles from './DeadlinePill.module.css';

export interface EventDates {
  /** First day (YYYY-MM-DD). */
  start: string;
  /** Last day (YYYY-MM-DD); omit for a one-day event. */
  end?: string | null;
}

export interface DeadlinePillProps {
  /** Closing date (YYYY-MM-DD). null: no deadline. Weight and wording come from the days left. */
  deadline?: string | null;
  /** Event dates: the pill shows the dates and its weight is counted from the start (decision 23). */
  event?: EventDates;
  /** Explicit wording. */
  label?: string;
  /** Wording when there is no deadline. */
  emptyText?: 'No deadline stated' | 'No deadline';
  /** regular: 13px (desktop list, detail, boards). small: 12px (phone feed rows). */
  size?: 'regular' | 'small';
  className?: string;
}

/** Deadlines escalate by weight, not hue. Missing and closed deadlines are plain text. */
export function DeadlinePill({ deadline, event, label, emptyText = 'No deadline stated', size = 'regular', className }: DeadlinePillProps) {
  const sized = (base: string | undefined, weight?: string) => cx(base, weight && styles[weight], styles[size], className);
  if (event) {
    if (eventEnded(event.start, event.end)) {
      // Not on the boards: an event that is over reads like a closed deadline.
      return <span className={sized(styles.plain)}>{label ?? `Ended ${formatShortDate(event.end ?? event.start)}`}</span>;
    }
    const weight = eventWeight(daysLeft(event.start));
    return <span className={sized(styles.pill, weight)}>{label ?? eventLabel(event.start, event.end)}</span>;
  }
  if (!deadline) {
    return <span className={sized(styles.plain)}>{label ?? emptyText}</span>;
  }
  const days = daysLeft(deadline);
  const text = label ?? deadlineLabel(deadline);
  if (days < 0) return <span className={sized(styles.plain)}>{text}</span>;
  return <span className={sized(styles.pill, deadlineWeight(days))}>{text}</span>;
}
