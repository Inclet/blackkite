import type { AnchorHTMLAttributes } from 'react';
import { cx } from '../../lib/streams';
import styles from './NavItem.module.css';

export interface NavItemProps extends Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'aria-current'> {
  /** side: desktop sidebar (44px, 15px). tab: phone bottom tab bar (48px, 12px, indicator bar). */
  variant: 'side' | 'tab';
  current?: boolean;
}

/** A main-navigation link. The current item carries aria-current="page". */
export function NavItem({ variant, current = false, className, children, ...rest }: NavItemProps) {
  return (
    <a {...rest} aria-current={current ? 'page' : undefined} className={cx(styles.item, styles[variant], current && styles.current, className)}>
      {variant === 'tab' && <span aria-hidden="true" className={styles.indicator} />}
      {children}
    </a>
  );
}
