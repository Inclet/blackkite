import type { ReactNode } from 'react';
import { useNavigate } from 'react-router';
import { api } from '../../api/client';
import { useResource } from '../../api/useResource';
import { AccountButton } from '../../components/AccountButton/AccountButton';
import { Kite } from '../../components/Kite/Kite';
import { NavItem } from '../../components/NavItem/NavItem';
import { Wordmark } from '../../components/Wordmark/Wordmark';
import { useAppLink } from '../../lib/useAppLink';
import { useIsDesktop } from '../../lib/useIsDesktop';
import styles from './AppShell.module.css';

/** The desktop sidebar: the board's five items, then the two settings screens (not on the board). */
export const SHELL_NAV = [
  { label: 'Feed', to: '/' },
  { label: 'Shortlist', to: '/shortlist' },
  { label: 'Calendar', to: '/calendar' },
  { label: 'Sources', to: '/sources' },
  { label: 'Profiles', to: '/profiles' },
  { label: 'Digest', to: '/settings/digest' },
  { label: 'Account', to: '/account' },
] as const;

/** The phone tab bar, as on feed-phone.html. Profiles, digest, account and sources live under More. */
export const SHELL_TABS = [
  { label: 'Feed', to: '/' },
  { label: 'Shortlist', to: '/shortlist' },
  { label: 'Calendar', to: '/calendar' },
  { label: 'More', to: '/more' },
] as const;

/** The nav item a path belongs to (/profiles/3 is under Profiles). */
export function currentFor(path: string, items: readonly { to: string }[]): string | null {
  const hit = items.filter((i) => i.to !== '/' && (path === i.to || path.startsWith(`${i.to}/`)));
  if (hit.length) return hit[0]!.to;
  return path === '/' || path.startsWith('/o/') ? '/' : null;
}

export interface AppShellProps {
  /** The screen's path, for the current nav item. */
  path: string;
  title: string;
  /** One line under the heading, slate (as the feed's summary). */
  summary?: string;
  children?: ReactNode;
}

/**
 * The frame for screens built without a board (Shortlist, Profiles, Digest,
 * Account, More): the feed boards' sidebar or header and tab bar, a heading and
 * a column of cards. Listed for design review.
 */
export function AppShell({ path, title, summary, children }: AppShellProps) {
  const desktop = useIsDesktop();
  const link = useAppLink();
  const navigate = useNavigate();
  const me = useResource('me', (s) => api.me(s));

  if (desktop) {
    const current = currentFor(path, SHELL_NAV);
    return (
      <div className={styles.page}>
        <nav aria-label="Main" className={styles.nav}>
          <div className={styles.lockup}>
            <Kite label="Blackkite" width={42} height={28} rotate={-16} />
            <Wordmark size={22} />
          </div>
          <div className={styles.navList}>
            {SHELL_NAV.map((n) => (
              <NavItem key={n.to} variant="side" current={n.to === current} {...link(n.to)}>
                {n.label}
              </NavItem>
            ))}
          </div>
        </nav>
        <main className={styles.main}>
          <div className={styles.greet}>
            <h1 tabIndex={-1} className={styles.h1}>
              {title}
            </h1>
            {summary && <div className={styles.summary}>{summary}</div>}
          </div>
          <div className={styles.body}>{children}</div>
        </main>
      </div>
    );
  }

  const tab = currentFor(path, SHELL_TABS) ?? '/more';
  return (
    <div className={styles.phonePage}>
      <header className={styles.header}>
        <div className={styles.phoneLockup}>
          <Kite label="Blackkite" width={39} height={26} rotate={-16} />
          <Wordmark size={20} />
        </div>
        <AccountButton name={me.data?.name ?? ''} email={me.data?.email} onClick={() => navigate('/account')} />
      </header>
      <main className={styles.phoneMain}>
        <div className={styles.phoneGreet}>
          <h1 tabIndex={-1} className={styles.phoneH1}>
            {title}
          </h1>
          {summary && <div className={styles.summary}>{summary}</div>}
        </div>
        <div className={styles.phoneBody}>{children}</div>
      </main>
      <nav aria-label="Main" className={styles.tabs}>
        {SHELL_TABS.map((t) => (
          <NavItem key={t.to} variant="tab" current={t.to === tab} {...link(t.to)}>
            {t.label}
          </NavItem>
        ))}
      </nav>
    </div>
  );
}
