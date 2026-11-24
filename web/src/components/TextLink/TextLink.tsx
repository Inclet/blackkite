import type { AnchorHTMLAttributes, ButtonHTMLAttributes } from 'react';
import { cx } from '../../lib/streams';
import styles from './TextLink.module.css';

export interface TextLinkProps extends AnchorHTMLAttributes<HTMLAnchorElement> {
  /** inline: beside buttons (12px 6px padding). stacked: under text in a card (8px 0). */
  spacing?: 'inline' | 'stacked';
}

/** An underlined text link. Its hit area is at least 44px high and wide (decision 2). */
export function TextLink({ spacing = 'inline', className, ...rest }: TextLinkProps) {
  return <a className={cx(styles.link, styles[spacing], className)} {...rest} />;
}

export interface TextButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  spacing?: 'inline' | 'stacked';
}

/** The text-link look for an action that goes nowhere (click only): a real button. */
export function TextButton({ spacing = 'inline', className, type = 'button', ...rest }: TextButtonProps) {
  return <button type={type} className={cx(styles.link, styles.button, styles[spacing], className)} {...rest} />;
}
