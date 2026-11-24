import { Button } from '../Button/Button';
import { Icon } from '../Icon/Icon';
import { Kite } from '../Kite/Kite';
import { KiteOrbit, ORBITS } from '../KiteOrbit/KiteOrbit';
import { TextButton, TextLink } from '../TextLink/TextLink';
import styles from './StateCard.module.css';

export type StateKind = 'checking' | 'nothing-new' | 'first-visit' | 'source-down';

export interface StateCardProps {
  kind: StateKind;
  title: string;
  body: string;
  /** Link when it has an href, otherwise a button (first visit: the primary button). Checking has none. */
  action?: { label: string; href?: string; onClick?: () => void };
}

/** The contents of a feed state: checking, nothing new, first visit, a source is down. */
export function StateCard({ kind, title, body, action }: StateCardProps) {
  if (kind === 'checking') {
    return (
      <div className={styles.checking} role="status">
        <KiteOrbit orbit={ORBITS.checking} />
        <div className={styles.checkingText}>
          <div className={styles.title}>{title}</div>
          <div className={styles.body}>{body}</div>
        </div>
      </div>
    );
  }
  return (
    <div className={styles.stack}>
      {kind === 'nothing-new' && <Kite width={48} height={32} fill="var(--bk-stone-300)" />}
      {kind === 'source-down' ? (
        <div className={styles.alertTitle}>
          <Icon name="conflict" size={18} stroke="var(--bk-alert-text)" strokeWidth={1.5} />
          {title}
        </div>
      ) : (
        <div className={styles.title}>{title}</div>
      )}
      <div className={styles.body}>{body}</div>
      {action &&
        (kind === 'first-visit' ? (
          <div className={styles.buttonRow}>
            <Button onClick={action.onClick}>{action.label}</Button>
          </div>
        ) : action.href !== undefined ? (
          <TextLink spacing="stacked" href={action.href} onClick={action.onClick}>
            {action.label}
          </TextLink>
        ) : (
          <TextButton spacing="stacked" onClick={action.onClick}>
            {action.label}
          </TextButton>
        ))}
    </div>
  );
}
