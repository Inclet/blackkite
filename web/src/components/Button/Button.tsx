import type { ButtonHTMLAttributes } from 'react';
import { cx } from '../../lib/streams';
import styles from './Button.module.css';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary';
  /** Styleguide only: draw the hover or keyboard-focus look without the interaction. */
  forceState?: 'hover' | 'focus';
}

export function Button({ variant = 'primary', forceState, className, type = 'button', ...rest }: ButtonProps) {
  return (
    <button
      type={type}
      className={cx(styles.button, styles[variant], forceState && styles[`force-${forceState}`], className)}
      {...rest}
    />
  );
}
