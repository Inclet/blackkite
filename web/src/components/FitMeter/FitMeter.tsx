import icons from '@design/assets/icons.json';
import { cx } from '../../lib/streams';
import styles from './FitMeter.module.css';

export type FitLevel = 'strong' | 'good' | 'possible';

const HEIGHTS = [6, 10, 14];

/** Three bars, bottom-aligned; filled bars graphite, empty stone-300. Decorative: the word carries the meaning. */
export function FitMeter({ level, className }: { level: FitLevel; className?: string }) {
  const filled: boolean[] = icons.fitMeter[level];
  return (
    <span aria-hidden="true" className={cx(styles.meter, className)} data-level={level}>
      {HEIGHTS.map((h, i) => (
        <span key={h} className={cx(styles.bar, filled[i] && styles.filled)} style={{ height: h }} />
      ))}
    </span>
  );
}
