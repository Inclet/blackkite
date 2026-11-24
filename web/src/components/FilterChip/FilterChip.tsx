import type { ButtonHTMLAttributes } from 'react';
import { cx, STREAM_COLOURS, STREAM_PLURALS, type Stream } from '../../lib/streams';
import { Icon } from '../Icon/Icon';
import styles from './FilterChip.module.css';

export interface FilterChipProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children'> {
  stream: Stream | 'all';
  selected: boolean;
  /** Defaults to "All" or the stream's plural name. */
  label?: string;
}

/** A feed filter. It fills with its stream colour only when selected. */
export function FilterChip({ stream, selected, label, className, type = 'button', ...rest }: FilterChipProps) {
  const text = label ?? (stream === 'all' ? 'All' : STREAM_PLURALS[stream]);
  return (
    <button
      type={type}
      aria-pressed={selected}
      className={cx(styles.chip, styles[stream], selected ? styles.selected : styles.unselected, className)}
      {...rest}
    >
      {stream !== 'all' && (
        <Icon
          name={stream}
          size={15}
          stroke={selected ? STREAM_COLOURS[stream].text : STREAM_COLOURS[stream].icon}
          strokeWidth={selected ? 1.4 : 1.6}
        />
      )}
      {text}
    </button>
  );
}
