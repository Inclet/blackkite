import type { AnchorHTMLAttributes } from 'react';
import { cx } from '../../lib/streams';
import { Icon } from '../Icon/Icon';
import styles from './BackLink.module.css';

/** "‹ Feed" at the top of a phone screen: 44px high, not underlined. */
export function BackLink({ className, children, ...rest }: AnchorHTMLAttributes<HTMLAnchorElement>) {
  return (
    <a {...rest} className={cx(styles.link, className)}>
      <Icon name="back" size={18} stroke="var(--bk-graphite)" strokeWidth={1.6} />
      {children}
    </a>
  );
}
