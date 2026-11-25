import { Kite } from '../../components/Kite/Kite';
import { NavItem } from '../../components/NavItem/NavItem';
import { Wordmark } from '../../components/Wordmark/Wordmark';
import { nextDigest } from '../../lib/feed';
import { useAppLink } from '../../lib/useAppLink';
import styles from './Sidebar.module.css';

/** The feed board's sidebar items, the same on every desktop screen. */
export const SIDEBAR_NAV = [
  { label: 'Feed', to: '/' },
  { label: 'Shortlist', to: '/shortlist' },
  { label: 'Calendar', to: '/calendar' },
  { label: 'Sources', to: '/sources' },
  { label: 'Profiles', to: '/profiles' },
] as const;

/**
 * feed-desktop.html's sidebar: lockup, the five items and the "Next digest" footer.
 * Used by the feed and by every other desktop screen (AppShell), so they match.
 */
export function Sidebar({ current, channel }: { current: string | null; channel: string }) {
  const link = useAppLink();
  return (
    <nav aria-label="Main" className={styles.nav}>
      <div className={styles.lockup}>
        <Kite label="Blackkite" width={42} height={28} rotate={-16} />
        <Wordmark size={22} />
      </div>
      <div className={styles.navList}>
        {SIDEBAR_NAV.map((n) => (
          <NavItem key={n.to} variant="side" current={n.to === current} {...link(n.to)}>
            {n.label}
          </NavItem>
        ))}
      </div>
      <div className={styles.digest}>
        <div className={styles.digestLabel}>Next digest</div>
        <div>{nextDigest(channel)}</div>
      </div>
    </nav>
  );
}
