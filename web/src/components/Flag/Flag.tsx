import type { ReactNode } from 'react';
import { cx } from '../../lib/streams';
import styles from './Flag.module.css';

/** Something to check before acting: a dashed outline. */
export function Flag({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cx(styles.flag, className)}>{children}</span>;
}
