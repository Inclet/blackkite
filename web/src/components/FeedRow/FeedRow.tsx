import type { MouseEvent } from 'react';
import { cx, STREAM_COLOURS, STREAM_NAMES, type Stream } from '../../lib/streams';
import { DeadlinePill, type DeadlinePillProps } from '../DeadlinePill/DeadlinePill';
import { FitLine } from '../FitLine/FitLine';
import type { FitLevel } from '../FitMeter/FitMeter';
import { Icon } from '../Icon/Icon';
import styles from './FeedRow.module.css';

export type FeedRowLayout = 'board' | 'list' | 'phone';

export interface FeedRowProps {
  stream: Stream;
  title: string;
  /** The second line. In list and phone layouts it already carries the fit word (decision 24). */
  subtitle: string;
  /** A fit level, "not-scored", or null for nothing (closed items). Shown as a column in the board layout only. */
  fit: FitLevel | 'not-scored' | null;
  deadline: Omit<DeadlinePillProps, 'className' | 'size'>;
  /** Closed items fade and lose their colour. */
  closed?: boolean;
  /**
   * board: the Components board's four columns (tile | text | fit | deadline).
   * list: the desktop feed list (tile | text | deadline), a link that can be selected.
   * phone: the phone feed (tile | title over subtitle and deadline), a link.
   */
  layout?: FeedRowLayout;
  /** list and phone: where the row leads. */
  href?: string;
  onClick?: (event: MouseEvent<HTMLAnchorElement>) => void;
  /** list: the row shown in the detail pane (aria-current). */
  selected?: boolean;
  /** Drops in once (--bk-settle); nothing moves with reduced motion. */
  isNew?: boolean;
  id?: string;
  className?: string;
}

function Tile({ stream, closed }: { stream: Stream; closed: boolean }) {
  const colours = STREAM_COLOURS[stream];
  return (
    <span className={styles.tile} style={{ background: closed ? 'var(--bk-stone-100)' : colours.tint }}>
      <Icon name={stream} label={STREAM_NAMES[stream]} size={18} strokeWidth={1.4} stroke={closed ? 'var(--bk-slate)' : colours.text} />
    </span>
  );
}

/** A feed row. Long titles cut at one line, except on the phone where they wrap. */
export function FeedRow({
  stream,
  title,
  subtitle,
  fit,
  deadline,
  closed = false,
  layout = 'board',
  href,
  onClick,
  selected = false,
  isNew = false,
  id,
  className,
}: FeedRowProps) {
  if (layout === 'board') {
    return (
      <div id={id} className={cx(styles.row, closed && styles.closed, className)}>
        <Tile stream={stream} closed={closed} />
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
  const common = {
    id,
    href,
    onClick,
    className: cx(styles.link, styles[layout], closed && styles.closed, selected && styles.selected, isNew && styles.new, className),
  };
  if (layout === 'list') {
    return (
      <a {...common} aria-current={selected ? 'true' : undefined}>
        <Tile stream={stream} closed={closed} />
        <span className={styles.text}>
          <span className={styles.title}>{title}</span>
          <span className={styles.subtitle}>{subtitle}</span>
        </span>
        <DeadlinePill {...deadline} />
      </a>
    );
  }
  return (
    <a {...common}>
      <Tile stream={stream} closed={closed} />
      <span className={styles.phoneBody}>
        <span className={styles.phoneTitle}>{title}</span>
        <span className={styles.phoneMeta}>
          <span className={styles.subtitle}>{subtitle}</span>
          <DeadlinePill {...deadline} size="small" />
        </span>
      </span>
    </a>
  );
}
