import { Card } from '../../components/Card/Card';
import { NavItem } from '../../components/NavItem/NavItem';
import { useAppLink } from '../../lib/useAppLink';
import { AppShell } from '../shell/AppShell';
import { ADMIN_NAV } from '../shell/Sidebar';
import { useIsAdmin } from '../shell/useIsAdmin';
import styles from './Settings.module.css';

export const MORE_LINKS = [
  { label: 'Profiles', to: '/profiles' },
  { label: 'Digest', to: '/settings/digest' },
  { label: 'Sources', to: '/sources' },
  { label: 'Account', to: '/account' },
] as const;

/** /more: the phone's fourth tab. The screens the tab bar has no room for (and Admin, for admins). Design review. */
export function More() {
  const link = useAppLink();
  const admin = useIsAdmin();
  const links = admin ? [...MORE_LINKS, ADMIN_NAV] : MORE_LINKS;
  return (
    <AppShell path="/more" title="More">
      <Card padding="12px" aria-label="More">
        <div className={styles.links}>
          {links.map((l) => (
            <NavItem key={l.to} variant="side" {...link(l.to)}>
              {l.label}
            </NavItem>
          ))}
        </div>
      </Card>
    </AppShell>
  );
}
