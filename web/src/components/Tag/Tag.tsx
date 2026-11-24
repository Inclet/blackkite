import type { ReactNode } from 'react';
import { cx, STREAM_NAMES, type Stream } from '../../lib/streams';
import { Icon } from '../Icon/Icon';
import styles from './Tag.module.css';

export type TagProps =
  | {
      kind: 'stream';
      stream: Stream;
      /** Leading stream icon (14px, 1.4, in the text shade). */
      icon?: boolean;
      /** Evening colours from the evening token set. */
      evening?: boolean;
      children?: ReactNode;
      className?: string;
    }
  | { kind: 'profile'; children: ReactNode; className?: string };

/** Stream tags carry the stream tint; profile tags stay neutral. */
export function Tag(props: TagProps) {
  if (props.kind === 'profile') {
    return <span className={cx(styles.tag, styles.profile, props.className)}>{props.children}</span>;
  }
  const { stream, icon, evening, children, className } = props;
  return (
    <span
      className={cx(styles.tag, styles[stream], icon && styles.withIcon, className)}
      data-theme={evening ? 'evening' : undefined}
    >
      {icon && <Icon name={stream} size={14} strokeWidth={1.4} stroke="currentColor" />}
      {children ?? STREAM_NAMES[stream]}
    </span>
  );
}
