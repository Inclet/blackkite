import type { ReactNode } from 'react';
import { cx } from '../../lib/streams';
import { Icon } from '../Icon/Icon';
import { FitMeter, type FitLevel } from '../FitMeter/FitMeter';
import styles from './FitLine.module.css';

const WORDS: Record<FitLevel, string> = { strong: 'Strong', good: 'Good', possible: 'Possible' };

export interface FitLineProps {
  level: FitLevel;
  /** The reason; without it the line is the compact row form (meter + word). */
  reason?: string;
  /** heading: the detail pane's "Strong fit · why this matched" (13px 600, one colour). */
  variant?: 'line' | 'heading';
  className?: string;
}

/** A fit word with its meter, and the reason. Never a bare score. */
export function FitLine({ level, reason, variant = 'line', className }: FitLineProps) {
  if (variant === 'heading') {
    return (
      <div className={cx(styles.heading, className)}>
        <FitMeter level={level} />
        {`${WORDS[level]} fit${reason ? ` · ${reason}` : ''}`}
      </div>
    );
  }
  if (reason === undefined) {
    return (
      <div className={cx(styles.compact, level === 'possible' && styles.muted, className)}>
        <FitMeter level={level} />
        {WORDS[level]}
      </div>
    );
  }
  return (
    <div className={cx(styles.line, className)}>
      <FitMeter level={level} />
      <strong className={styles.word}>{WORDS[level]}</strong>
      <span className={styles.reason}>{reason}</span>
    </div>
  );
}

/** One reason under a fit heading: a check mark and a sentence (14px, 1.45). */
export function FitReason({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cx(styles.fitReason, className)}>
      <Icon name="check" size={16} stroke="var(--bk-graphite)" strokeWidth={1.6} className={styles.check} />
      <span>{children}</span>
    </div>
  );
}
