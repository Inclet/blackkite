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

export interface TrustPanelProps {
  state: TrustState;
  /** Defaults to the state's standard wording. */
  title?: ReactNode;
  /** What we know and what to check. */
  children: ReactNode;
  /** mist on the desktop detail pane, stone on the phone (the boards differ). */
  tone?: 'mist' | 'stone';
  className?: string;
}

/** The inset trust panel: icon and state, then one or two sentences. */
export function TrustPanel({ state, title, children, tone = 'mist', className }: TrustPanelProps) {
  return (
    <div className={cx(styles.panel, styles[tone], className)}>
      <div className={cx(styles.panelTitle, state === 'conflict' && styles.conflict)}>
        <Icon name={state} size={16} stroke={STROKES[state]} strokeWidth={1.5} />
        {title ?? DEFAULT_TEXT[state]}
      </div>
      <div className={styles.panelBody}>{children}</div>
    </div>
  );
}
