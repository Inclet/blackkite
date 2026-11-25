import type { ButtonHTMLAttributes, Ref } from 'react';
import { cx, STREAM_COLOURS, STREAM_PLURALS, type Stream } from '../../lib/streams';
import { Icon } from '../Icon/Icon';
import styles from './FilterChip.module.css';

interface BaseProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children' | 'aria-pressed'> {
  stream: Stream | 'all';
  /** Defaults to "All" or the stream's plural name. */
  label?: string;
  ref?: Ref<HTMLButtonElement>;
}

/**
 * A toggle (`selected`, announced with aria-pressed), or with `action` a one-shot
 * button in the unselected look: no pressed state, so screen readers do not
 * announce a toggle (the dismiss reasons).
 */
export type FilterChipProps = BaseProps & ({ selected: boolean; action?: false } | { action: true; selected?: never });

/** A feed filter. It fills with its stream colour only when selected. */
export function FilterChip({ stream, selected = false, action = false, label, className, type = 'button', ...rest }: FilterChipProps) {
  const text = label ?? (stream === 'all' ? 'All' : STREAM_PLURALS[stream]);
  return (
    <button
      type={type}
      aria-pressed={action ? undefined : selected}
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
