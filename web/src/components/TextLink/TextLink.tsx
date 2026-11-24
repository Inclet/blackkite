import type { AnchorHTMLAttributes } from 'react';
import { cx } from '../../lib/streams';
import styles from './TextLink.module.css';

export interface TextLinkProps extends AnchorHTMLAttributes<HTMLAnchorElement> {
  /** inline: beside buttons (12px 6px padding). stacked: under text in a card (8px 0). */
  spacing?: 'inline' | 'stacked';
}

/** An underlined text link. Its hit area is at least 44px high (decision 2). */
export function TextLink({ spacing = 'inline', className, ...rest }: TextLinkProps) {
  return <a className={cx(styles.link, styles[spacing], className)} {...rest} />;
}
