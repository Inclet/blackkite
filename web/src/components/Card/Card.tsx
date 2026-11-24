import type { CSSProperties, ReactNode } from 'react';
import { cx } from '../../lib/streams';
import styles from './Card.module.css';

export interface CardProps {
  /** Board label at the top (12px, slate). */
  label?: ReactNode;
  /** CSS padding, e.g. "22px 24px". */
  padding?: string;
  /** Gap between children, px. */
  gap?: number;
  /** The element: section (default), article (the detail pane) or div. */
  as?: 'section' | 'article' | 'div';
  className?: string;
  style?: CSSProperties;
  children?: ReactNode;
  'aria-label'?: string;
  'aria-labelledby'?: string;
}

/** The white 14px-radius panel. */
export function Card({ label, padding = '22px 24px', gap, as: Tag = 'section', className, style, children, ...aria }: CardProps) {
  return (
    <Tag {...aria} className={cx(styles.card, className)} style={{ padding, gap, ...style }}>
      {label !== undefined && <CardLabel>{label}</CardLabel>}
      {children}
    </Tag>
  );
}

export function CardLabel({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cx(styles.label, className)}>{children}</div>;
}
