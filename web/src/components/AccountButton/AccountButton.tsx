import type { ButtonHTMLAttributes } from 'react';
import { cx } from '../../lib/streams';
import styles from './AccountButton.module.css';

export interface AccountButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children' | 'aria-label'> {
  /** The user's name; the button shows its first letter. */
  name: string;
  /** The account email (GET /me): its first letter when there is no name. */
  email?: string;
}

/** The letter on the button: the name's first, else the email's, else nothing. */
export function accountInitial(name: string, email?: string): string {
  return (name.trim() || email?.trim() || '').charAt(0).toUpperCase();
}

/** The phone header's round account button (44px). */
export function AccountButton({ name, email, className, type = 'button', ...rest }: AccountButtonProps) {
  return (
    <button {...rest} type={type} aria-label="Your account" className={cx(styles.button, className)}>
      {accountInitial(name, email)}
    </button>
  );
}
