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
import { ADMIN_NAV, Sidebar, SIDEBAR_NAV } from './Sidebar';

/**
 * Settings screens reached from Profiles (and the phone's More), not from the sidebar:
 * on desktop they keep Profiles current.
 */
const UNDER_PROFILES = ['/settings/digest', '/account'];

/** The sidebar item a desktop path belongs to. */
export function sidebarCurrent(path: string): string | null {
  if (UNDER_PROFILES.some((p) => path === p || path.startsWith(`${p}/`))) return '/profiles';
  if (path === ADMIN_NAV.to || path.startsWith(`${ADMIN_NAV.to}/`)) return ADMIN_NAV.to;
  return currentFor(path, SIDEBAR_NAV);
}

/** The phone tab bar, as on feed-phone.html. Profiles, digest, account, sources and admin live under More. */
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
  /** Desktop: let the content column use the whole main area (the calendar's month grid). */
  wide?: boolean;
  children?: ReactNode;
}

/**
 * The frame for screens built without a board (Shortlist, Profiles, Digest,
 * Account, More): the feed boards' sidebar or header and tab bar, a heading and
 * a column of cards. Listed for design review.
 */
export function AppShell({ path, title, summary, wide = false, children }: AppShellProps) {
  const desktop = useIsDesktop();
  const link = useAppLink();
  const navigate = useNavigate();
  const me = useResource('me', (s) => api.me(s));

  if (desktop) {
    return (
      <div className={styles.page}>
        {/* The digest goes by email in v1 (spec 8), as the feed's footer says. */}
        <Sidebar current={sidebarCurrent(path)} channel="email" />
        <main className={styles.main}>
          <div className={styles.greet}>
            <h1 tabIndex={-1} className={styles.h1}>
              {title}
            </h1>
            {summary && <div className={styles.summary}>{summary}</div>}
          </div>
          <div className={wide ? `${styles.body} ${styles.wide}` : styles.body}>{children}</div>
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
