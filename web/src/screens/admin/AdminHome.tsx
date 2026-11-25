import { Card } from '../../components/Card/Card';
import { NavItem } from '../../components/NavItem/NavItem';
import { useAppLink } from '../../lib/useAppLink';
import { AppShell } from '../shell/AppShell';
import settingsStyles from '../settings/Settings.module.css';
import { ADMIN_LINKS, AdminOnly } from './AdminOnly';

export const ADMIN_HOME_SUMMARY = 'Sources, suggestions from members, items to review, and who can sign in.';

/** /admin: the admin screens, as a card of NavItems (as More). Design review. */
export function AdminHome() {
  return (
    <AdminOnly path="/admin" title="Admin">
      <Home />
    </AdminOnly>
  );
}

function Home() {
  const link = useAppLink();
  return (
    <AppShell path="/admin" title="Admin" summary={ADMIN_HOME_SUMMARY}>
      <Card padding="12px" aria-label="Admin screens">
        <div className={settingsStyles.links}>
          {ADMIN_LINKS.map((l) => (
            <NavItem key={l.to} variant="side" {...link(l.to)}>
              {l.label}
            </NavItem>
          ))}
        </div>
      </Card>
    </AppShell>
  );
}
