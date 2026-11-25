import type { ReactNode } from 'react';
import { api, type ApiError } from '../../api/client';
import { useResource } from '../../api/useResource';
import { BackLink } from '../../components/BackLink/BackLink';
import { Card } from '../../components/Card/Card';
import { useAppLink } from '../../lib/useAppLink';
import { LoadState } from '../common/LoadState';
import { AppShell } from '../shell/AppShell';
import { SignIn } from '../SignIn';
import styles from '../sources/Sources.module.css';

export const ADMIN_ONLY = 'This page is for admins.';

/** The admin screens (spec 3, 8). Each has a back link to /admin. */
export const ADMIN_LINKS = [
  { label: 'Sources', to: '/admin/sources' },
  { label: 'Suggestions', to: '/admin/suggestions' },
  { label: 'Review', to: '/admin/review' },
  { label: 'Users', to: '/admin/users' },
] as const;

/** The plain refusal non-admins see (and anyone the admin API answers 403). */
export function NotAdmin({ path }: { path: string }) {
  return (
    <AppShell path={path} title="Admin">
      <Card aria-label="Admin">
        <div className={styles.status}>{ADMIN_ONLY}</div>
      </Card>
    </AppShell>
  );
}

/**
 * Renders `children` only for an admin session; their data hooks never run for
 * anyone else. The server enforces the role regardless (spec 3).
 */
export function AdminOnly({ path, title, children }: { path: string; title: string; children: ReactNode }) {
  const me = useResource('me', (s) => api.me(s));
  if (me.error?.kind === 'unauthorized') return <SignIn />;
  if (!me.data) {
    return (
      <AppShell path={path} title={title}>
        <LoadState loading={me.loading} error={me.error} onRetry={me.reload} />
      </AppShell>
    );
  }
  if (me.data.role !== 'admin') return <NotAdmin path={path} />;
  return <>{children}</>;
}

/**
 * What an admin screen shows for a failed load: sign-in (401), the refusal (403),
 * or nothing (the screen's LoadState says the rest). Null means carry on.
 */
export function adminFailure(path: string, ...errors: (ApiError | null)[]): ReactNode | null {
  if (errors.some((e) => e?.kind === 'unauthorized')) return <SignIn />;
  if (errors.some((e) => e?.kind === 'forbidden')) return <NotAdmin path={path} />;
  return null;
}

/** "‹ Admin" at the top of each admin screen. */
export function BackToAdmin({ to = '/admin', label = 'Admin' }: { to?: string; label?: string }) {
  const link = useAppLink();
  return (
    <div>
      <BackLink {...link(to)}>{label}</BackLink>
    </div>
  );
}
