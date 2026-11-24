import type { ButtonHTMLAttributes } from 'react';
import { cx } from '../../lib/streams';
import styles from './AccountButton.module.css';

export interface AccountButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children' | 'aria-label'> {
  /** The user's name; the button shows its first letter. */
  name: string;
}

/** The phone header's round account button (44px). */
export function AccountButton({ name, className, type = 'button', ...rest }: AccountButtonProps) {
  return (
    <button {...rest} type={type} aria-label="Your account" className={cx(styles.button, className)}>
      {name.trim().charAt(0).toUpperCase()}
    </button>
  );
}
