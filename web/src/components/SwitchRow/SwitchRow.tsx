import { useId } from 'react';
import { cx } from '../../lib/streams';
import { Switch } from '../Switch/Switch';
import styles from './SwitchRow.module.css';

export interface SwitchRowProps {
  label: string;
  description?: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  /** Locked: shown, not changeable (e.g. once an admin published a private item). */
  disabled?: boolean;
  className?: string;
}

/** A label, a one-line description and a Switch, as the Components board's "Urgent alerts". */
export function SwitchRow({ label, description, checked, onChange, disabled, className }: SwitchRowProps) {
  const id = useId();
  return (
    <div className={cx(styles.row, className)}>
      <div className={styles.text}>
        <div className={styles.label}>{label}</div>
        {description && (
          <div id={id} className={styles.description}>
            {description}
          </div>
        )}
      </div>
      <Switch checked={checked} onChange={onChange} label={label} disabled={disabled} aria-describedby={description ? id : undefined} />
    </div>
  );
}
