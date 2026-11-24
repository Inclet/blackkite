import type { ReactNode } from 'react';
import { cx } from '../../lib/streams';
import { Icon } from '../Icon/Icon';
import styles from './TrustNote.module.css';

export type TrustState = 'confirmed' | 'unconfirmed' | 'conflict';

const STROKES: Record<TrustState, string> = {
  confirmed: 'var(--bk-graphite)',
  unconfirmed: 'var(--bk-slate)',
  conflict: 'var(--bk-alert-text)',
};
const DEFAULT_TEXT: Record<TrustState, string> = {
  confirmed: 'Confirmed at the source',
  unconfirmed: 'Not yet confirmed at the source',
  conflict: 'Sources disagree on the date',
};

/** Where an item stands: confirmed at the source, not yet confirmed, or sources disagree. */
export function TrustNote({ state, children, className }: { state: TrustState; children?: ReactNode; className?: string }) {
  return (
    <span className={cx(styles.note, styles[state], className)}>
      <Icon name={state} size={16} stroke={STROKES[state]} strokeWidth={1.5} />
      {children ?? DEFAULT_TEXT[state]}
    </span>
  );
}
