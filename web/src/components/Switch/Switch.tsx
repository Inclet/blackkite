import type { ButtonHTMLAttributes } from 'react';
import { cx } from '../../lib/streams';
import styles from './Switch.module.css';

export interface SwitchProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'onChange' | 'role'> {
  checked: boolean;
  onChange?: (checked: boolean) => void;
  /** Accessible name. */
  label: string;
}

/** 48 x 28 visible; the hit area is extended to 44px high (decision 2). */
export function Switch({ checked, onChange, label, className, onClick, ...rest }: SwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      className={cx(styles.switch, checked && styles.on, className)}
      onClick={(e) => {
        onClick?.(e);
        onChange?.(!checked);
      }}
      {...rest}
    >
      <span className={styles.thumb} />
    </button>
  );
}
