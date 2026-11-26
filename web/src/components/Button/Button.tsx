import type { ButtonHTMLAttributes, Ref } from 'react';
import { cx } from '../../lib/streams';
import styles from './Button.module.css';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary';
  /** large: the phone's sticky action bar (48px, 15px). */
  size?: 'regular' | 'large';
  /** Styleguide only: draw the hover or keyboard-focus look without the interaction. */
  forceState?: 'hover' | 'focus';
  ref?: Ref<HTMLButtonElement>;
}

export function Button({ variant = 'primary', size = 'regular', forceState, className, type = 'button', ...rest }: ButtonProps) {
  return (
    <button
      type={type}
      className={cx(styles.button, styles[variant], size === 'large' && styles.large, forceState && styles[`force-${forceState}`], className)}
      {...rest}
    />
  );
}
