import { DeadlinePill } from '../../components/DeadlinePill/DeadlinePill';
import { FilterChip } from '../../components/FilterChip/FilterChip';
import { FitLine, FitReason } from '../../components/FitLine/FitLine';
import { Flag } from '../../components/Flag/Flag';
import { Tag } from '../../components/Tag/Tag';
import type { FeedItem } from '../../fixtures/types';
import { pillFor } from '../../lib/feed';
import { cx, STREAMS, type Stream } from '../../lib/streams';
import type { FeedModel } from './model';
import styles from './parts.module.css';

/** All, then the four streams (the desktop board shows all four; the phone's Events chip scrolls off-screen, decision 4). */
export function FilterChips({ model, className, chipClassName }: { model: FeedModel; className?: string; chipClassName?: string }) {
  const options: (Stream | 'all')[] = ['all', ...STREAMS];
  return (
    <div className={className} role="group" aria-label="Filter by stream">
      {options.map((s) => (
        <FilterChip key={s} stream={s} selected={model.filter === s} onClick={() => model.setFilter(s)} className={chipClassName} />
      ))}
    </div>
  );
}

/** Stream tag, profile tag and the deadline pill. */
export function DetailTop({ item, tagGap }: { item: FeedItem; tagGap: 6 | 8 }) {
  return (
    <div className={cx(styles.top, tagGap === 6 ? styles.topPhone : undefined)}>
      <span className={styles.tags}>
        <Tag kind="stream" stream={item.stream} />
        {item.detail.profile && <Tag kind="profile">{item.detail.profile}</Tag>}
      </span>
      <DeadlinePill {...pillFor(item)} />
    </div>
  );
}

/** "Strong fit · why this matched", the reasons and the "To check" note. Nothing for unscored items. */
export function FitSection({ item }: { item: FeedItem }) {
  if (!item.fit || item.fit === 'not-scored') return null;
  return (
    <>
      <FitLine level={item.fit} variant="heading" reason="why this matched" />
      {item.detail.reasons.map((r) => (
        <FitReason key={r}>{r}</FitReason>
      ))}
      {item.detail.toCheck && <Flag variant="note">{item.detail.toCheck}</Flag>}
    </>
  );
}

export function hasFitSection(item: FeedItem): boolean {
  return item.fit !== null && item.fit !== 'not-scored';
}

/** Announces save and dismiss to screen readers. */
export function LiveRegion({ message }: { message: string }) {
  return (
    <div role="status" aria-live="polite" className={styles.visuallyHidden}>
      {message}
    </div>
  );
}
