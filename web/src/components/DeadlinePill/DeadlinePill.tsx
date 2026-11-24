import { cx } from '../../lib/streams';
import { daysLeft, deadlineLabel, deadlineWeight, type DeadlineWeight } from '../../lib/deadline';
import styles from './DeadlinePill.module.css';

export interface DeadlinePillProps {
  /** Closing date (YYYY-MM-DD). null: no deadline. Weight and wording come from the days left. */
  deadline?: string | null;
  /** Explicit weight. Events use this until the event urgency rule is decided (decision 1). */
  weight?: DeadlineWeight;
  /** Explicit wording (needed with weight when there is no deadline date). */
  label?: string;
  /** Wording when there is no deadline. */
  emptyText?: 'No deadline stated' | 'No deadline';
  className?: string;
}

/** Deadlines escalate by weight, not hue. Missing and closed deadlines are plain text. */
export function DeadlinePill({ deadline, weight, label, emptyText = 'No deadline stated', className }: DeadlinePillProps) {
  if (weight) {
    return <span className={cx(styles.pill, styles[weight], className)}>{label ?? (deadline ? deadlineLabel(deadline) : '')}</span>;
  }
  if (!deadline) {
    return <span className={cx(styles.plain, className)}>{label ?? emptyText}</span>;
  }
  const days = daysLeft(deadline);
  const text = label ?? deadlineLabel(deadline);
  if (days < 0) return <span className={cx(styles.plain, className)}>{text}</span>;
  return <span className={cx(styles.pill, styles[deadlineWeight(days)], className)}>{text}</span>;
}
