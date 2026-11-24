import { cx, STREAM_COLOURS, STREAM_NAMES, type Stream } from '../../lib/streams';
import { DeadlinePill, type DeadlinePillProps } from '../DeadlinePill/DeadlinePill';
import { FitLine } from '../FitLine/FitLine';
import type { FitLevel } from '../FitMeter/FitMeter';
import { Icon } from '../Icon/Icon';
import styles from './FeedRow.module.css';

export interface FeedRowProps {
  stream: Stream;
  title: string;
  subtitle: string;
  /** A fit level, "not-scored", or null for nothing (closed items). */
  fit: FitLevel | 'not-scored' | null;
  deadline: Omit<DeadlinePillProps, 'className'>;
  /** Closed items fade and lose their colour. */
  closed?: boolean;
  className?: string;
}

/** The four-column feed row: 36px tile | title and subtitle | fit | deadline. Long text cuts at one line. */
export function FeedRow({ stream, title, subtitle, fit, deadline, closed = false, className }: FeedRowProps) {
  const colours = STREAM_COLOURS[stream];
  return (
    <div className={cx(styles.row, closed && styles.closed, className)}>
      <div className={styles.tile} style={{ background: closed ? 'var(--bk-stone-100)' : colours.tint }}>
        <Icon name={stream} label={STREAM_NAMES[stream]} size={18} strokeWidth={1.4} stroke={closed ? 'var(--bk-slate)' : colours.text} />
      </div>
      <div className={styles.text}>
        <div className={styles.title}>{title}</div>
        <div className={styles.subtitle}>{subtitle}</div>
      </div>
      {fit === null || fit === 'not-scored' ? (
        <div className={styles.unscored}>{fit === 'not-scored' ? 'Not scored' : ''}</div>
      ) : (
        <FitLine level={fit} />
      )}
      <DeadlinePill {...deadline} className={styles.deadline} />
    </div>
  );
}
