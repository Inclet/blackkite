import { useState, type FormEvent } from 'react';
import { api, ApiError } from '../../api/client';
import { sourcesApi, type AdminUser, type Invite } from '../../api/sources';
import { useResource } from '../../api/useResource';
import { Button } from '../../components/Button/Button';
import { Card } from '../../components/Card/Card';
import { Field } from '../../components/Field/Field';
import { Tag } from '../../components/Tag/Tag';
import { COPY } from '../common/copy';
import { LoadState } from '../common/LoadState';
import { AppShell } from '../shell/AppShell';
import styles from '../sources/Sources.module.css';
import { formatDay } from '../sources/words';
import { adminFailure, AdminOnly, BackToAdmin } from './AdminOnly';

export const USERS_COPY = {
  title: 'Users',
  summary: 'Who can sign in. Blackkite is invite-only: invite someone by email, or deactivate an account.',
  invite: 'Invite someone',
  email: 'Email address',
  send: 'Send invite',
  emailInvalid: 'Enter an email address, such as name@example.rw.',
  sent: (email: string) => `Invite sent to ${email}.`,
  already: 'That address already has an account.',
  refused: 'Blackkite did not accept that address.',
  inviteUnreachable: `${COPY.unreachableTitle}. The invite was not sent; try again.`,
  users: 'Accounts',
  you: 'You',
  admin: 'Admin',
  member: 'Member',
  active: 'Active',
  deactivated: 'Deactivated',
  joined: (when: string) => `Joined ${when}`,
  lastSignIn: (when: string) => `Last signed in ${when}`,
  neverSignedIn: 'Never signed in',
  makeAdmin: 'Make admin',
  makeMember: 'Make member',
  roleChanged: (email: string, role: string) => `${email} is now ${role === 'admin' ? 'an admin' : 'a member'}.`,
  lastAdmin: 'Blackkite needs at least one active admin, so nothing changed.',
  roleUnreachable: `${COPY.unreachableTitle}. The role did not change; try again.`,
  deactivate: 'Deactivate',
  confirm: (email: string) => `Deactivate ${email}? They are signed out and cannot sign in again.`,
  confirmButton: 'Deactivate this account',
  keep: 'Keep it',
  didDeactivate: (email: string) => `${email} is deactivated.`,
  deactivateUnreachable: `${COPY.unreachableTitle}. The account was not changed; try again.`,
  invites: 'Invites',
  pending: (when: string) => `Waiting · expires ${when}`,
  expired: (when: string) => `Expired ${when}`,
  accepted: (when: string) => `Accepted ${when}`,
  withdraw: 'Withdraw',
  withdrawn: (email: string) => `Invite to ${email} withdrawn.`,
  withdrawUnreachable: `${COPY.unreachableTitle}. The invite was not withdrawn; try again.`,
} as const;

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** /admin/users: accounts with role and status, invites, deactivation (spec 3). Design review. */
export function AdminUsers() {
  return (
    <AdminOnly path="/admin/users" title={USERS_COPY.title}>
      <Users />
    </AdminOnly>
  );
}

function Users() {
  const me = useResource('me', (s) => api.me(s));
  const users = useResource('admin-users', (s) => sourcesApi.users(s));
  const invites = useResource('admin-invites', (s) => sourcesApi.invites(s));
  const [message, setMessage] = useState<{ text: string; alert: boolean } | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);
  const failed = adminFailure('/admin/users', users.error, invites.error);
  if (failed) return failed;

  const deactivate = async (u: AdminUser) => {
    setMessage(null);
    try {
      const done = await sourcesApi.deactivate(u.id);
      users.setData((list) => list?.map((x) => (x.id === u.id ? { ...x, ...done } : x)));
      setConfirming(null);
      setMessage({ text: USERS_COPY.didDeactivate(u.email), alert: false });
    } catch (err) {
      setMessage({ text: err instanceof ApiError && err.kind === 'conflict' ? USERS_COPY.lastAdmin : USERS_COPY.deactivateUnreachable, alert: true });
    }
  };

  /** PATCH /api/admin/users/{id} {role} (contract 4.1; for the owner to confirm). */
  const changeRole = async (u: AdminUser) => {
    setMessage(null);
    const role = u.role === 'admin' ? 'member' : 'admin';
    try {
      const done = await sourcesApi.setRole(u.id, role);
      users.setData((list) => list?.map((x) => (x.id === u.id ? { ...x, ...done } : x)));
      setMessage({ text: USERS_COPY.roleChanged(u.email, done.role ?? role), alert: false });
    } catch (err) {
      setMessage({ text: err instanceof ApiError && err.kind === 'conflict' ? USERS_COPY.lastAdmin : USERS_COPY.roleUnreachable, alert: true });
    }
  };

  const withdraw = async (i: Invite) => {
    setMessage(null);
    try {
      await sourcesApi.withdrawInvite(i.id);
      invites.setData((list) => list?.filter((x) => x.id !== i.id));
      setMessage({ text: USERS_COPY.withdrawn(i.email), alert: false });
    } catch {
      setMessage({ text: USERS_COPY.withdrawUnreachable, alert: true });
    }
  };

  return (
    <AppShell path="/admin/users" title={USERS_COPY.title} summary={USERS_COPY.summary}>
      <BackToAdmin />
      <InviteForm onSent={(i) => invites.setData((list) => [i, ...(list ?? []).filter((x) => x.id !== i.id)])} />
      <LoadState loading={users.loading} error={users.error ?? invites.error} onRetry={() => (users.reload(), invites.reload())} />
      <div role="status" className={message?.alert ? styles.alertStatus : styles.status}>
        {message?.text ?? ''}
      </div>
      {users.data && (
        <Card label={USERS_COPY.users} padding="22px 24px 12px" gap={4} aria-label={USERS_COPY.users}>
          <div className={styles.rows}>
            {users.data.map((u) => {
              const self = u.id === me.data?.id;
              return (
                <div key={u.id} className={styles.stackRow}>
                  <div className={styles.row} style={{ padding: 0 }}>
                    <div className={styles.rowText}>
                      <span className={styles.rowTitle}>{u.name || u.email}</span>
                      <span className={styles.meta}>
                        {[
                          u.name ? u.email : null,
                          USERS_COPY.joined(formatDay(u.createdAt)),
                          u.lastSignInAt === undefined ? null : u.lastSignInAt ? USERS_COPY.lastSignIn(formatDay(u.lastSignInAt)) : USERS_COPY.neverSignedIn,
                        ]
                          .filter(Boolean)
                          .join(' · ')}
                      </span>
                    </div>
                    <div className={styles.side}>
                      {self && <Tag kind="profile">{USERS_COPY.you}</Tag>}
                      <Tag kind="profile">{u.role === 'admin' ? USERS_COPY.admin : USERS_COPY.member}</Tag>
                      <Tag kind="profile">{u.status === 'active' ? USERS_COPY.active : USERS_COPY.deactivated}</Tag>
                      {!self && u.status === 'active' && (
                        <Button variant="secondary" onClick={() => void changeRole(u)} aria-label={`${u.role === 'admin' ? USERS_COPY.makeMember : USERS_COPY.makeAdmin}: ${u.email}`}>
                          {u.role === 'admin' ? USERS_COPY.makeMember : USERS_COPY.makeAdmin}
                        </Button>
                      )}
                      {!self && u.status === 'active' && confirming !== u.id && (
                        <Button variant="secondary" onClick={() => setConfirming(u.id)} aria-label={`${USERS_COPY.deactivate} ${u.email}`}>
                          {USERS_COPY.deactivate}
                        </Button>
                      )}
                    </div>
                  </div>
                  {confirming === u.id && (
                    <>
                      <div className={styles.status}>{USERS_COPY.confirm(u.email)}</div>
                      <div className={styles.actions}>
                        <Button onClick={() => void deactivate(u)}>{USERS_COPY.confirmButton}</Button>
                        <Button variant="secondary" onClick={() => setConfirming(null)}>
                          {USERS_COPY.keep}
                        </Button>
                      </div>
                    </>
                  )}
                </div>
              );
            })}
          </div>
        </Card>
      )}
      {invites.data && invites.data.length > 0 && (
        <Card label={USERS_COPY.invites} padding="22px 24px 12px" gap={4} aria-label={USERS_COPY.invites}>
          <div className={styles.rows}>
            {invites.data.map((i) => (
              <div key={i.id} className={styles.row}>
                <div className={styles.rowText}>
                  <span className={styles.rowTitle}>{i.email}</span>
                  <span className={styles.meta}>
                    {i.status === 'accepted'
                      ? USERS_COPY.accepted(formatDay(i.acceptedAt))
                      : i.status === 'expired'
                        ? USERS_COPY.expired(formatDay(i.expiresAt))
                        : USERS_COPY.pending(formatDay(i.expiresAt))}
                  </span>
                </div>
                {i.status !== 'accepted' && (
                  <Button variant="secondary" onClick={() => void withdraw(i)} aria-label={`${USERS_COPY.withdraw} the invite to ${i.email}`}>
                    {USERS_COPY.withdraw}
                  </Button>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}
    </AppShell>
  );
}

function InviteForm({ onSent }: { onSent: (i: Invite) => void }) {
  const [email, setEmail] = useState('');
  const [error, setError] = useState<string | undefined>();
  const [status, setStatus] = useState<{ text: string; alert: boolean; busy?: boolean }>({ text: '', alert: false });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const value = email.trim();
    if (!EMAIL.test(value)) {
      setError(USERS_COPY.emailInvalid);
      setStatus({ text: '', alert: false });
      return;
    }
    setError(undefined);
    setStatus({ text: '', alert: false, busy: true });
    try {
      const invite = await sourcesApi.invite(value);
      onSent(invite);
      setEmail('');
      setStatus({ text: USERS_COPY.sent(value), alert: false });
    } catch (err) {
      const kind = err instanceof ApiError ? err.kind : 'unreachable';
      setStatus({
        text: kind === 'conflict' ? USERS_COPY.already : kind === 'invalid' ? USERS_COPY.refused : USERS_COPY.inviteUnreachable,
        alert: true,
      });
    }
  };

  return (
    <Card label={USERS_COPY.invite} gap={14}>
      <form onSubmit={submit} noValidate aria-label={USERS_COPY.invite} className={styles.form}>
        <Field label={USERS_COPY.email} name="email" type="email" autoComplete="off" value={email} error={error} onChange={(e) => setEmail(e.target.value)} />
        <div className={styles.actions}>
          <Button type="submit" disabled={status.busy}>
            {USERS_COPY.send}
          </Button>
        </div>
        <div role="status" className={status.alert ? styles.alertStatus : styles.status}>
          {status.text}
        </div>
      </form>
    </Card>
  );
}
