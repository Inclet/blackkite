import { cx } from '../../lib/streams';
import { FitMeter, type FitLevel } from '../FitMeter/FitMeter';
import styles from './FitLine.module.css';

const WORDS: Record<FitLevel, string> = { strong: 'Strong', good: 'Good', possible: 'Possible' };

export interface FitLineProps {
  level: FitLevel;
  /** The reason; without it the line is the compact row form (meter + word). */
  reason?: string;
  className?: string;
}

/** A fit word with its meter, and the reason. Never a bare score. */
export function FitLine({ level, reason, className }: FitLineProps) {
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
