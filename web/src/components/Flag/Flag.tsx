import type { ReactNode } from 'react';
import { cx } from '../../lib/streams';
import styles from './Flag.module.css';

export interface FlagProps {
  /** chip: a short label (Components board). note: a full "To check" sentence (detail pane). */
  variant?: 'chip' | 'note';
  children: ReactNode;
  className?: string;
}

/** Something to check before acting: a dashed outline. */
export function Flag({ variant = 'chip', children, className }: FlagProps) {
  if (variant === 'note') return <div className={cx(styles.note, className)}>{children}</div>;
  return <span className={cx(styles.flag, className)}>{children}</span>;
}
