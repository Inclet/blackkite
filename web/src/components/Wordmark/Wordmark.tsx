import styles from './Wordmark.module.css';

export interface WordmarkProps {
  /** Font size in px. */
  size?: number;
  className?: string;
}

/** "blackkite": Figtree 600, -0.025em, with the kk pair at -0.045em. */
export function Wordmark({ size = 36, className }: WordmarkProps) {
  return (
    <div className={[styles.wordmark, className].filter(Boolean).join(' ')} style={{ fontSize: size }}>
      blac<span className={styles.kk}>kk</span>ite
    </div>
  );
}
