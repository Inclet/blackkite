import { useState } from 'react';
import { useNavigate } from 'react-router';
import { api } from '../../api/client';
import { clearApiCache, useResource } from '../../api/useResource';
import { Button } from '../../components/Button/Button';
import { Card } from '../../components/Card/Card';
import { Field } from '../../components/Field/Field';
import { COPY } from '../common/copy';
import { LoadState } from '../common/LoadState';
import { AppShell } from '../shell/AppShell';
import { SignIn } from '../SignIn';
import styles from './Settings.module.css';

export const ACCOUNT_COPY = {
  title: 'Account',
  signedIn: 'Signed in as',
  signOut: 'Sign out',
  exportLabel: 'Your data',
  exportBody: 'Download everything Blackkite holds about you: profiles, saved items, notes and digest settings, as one file.',
  export: 'Export my data',
  exported: 'Your export has downloaded.',
  deleteLabel: 'Delete my account',
  deleteBody: 'This deletes your profiles, saved items, notes and settings. It cannot be undone.',
  delete: 'Delete my account',
  confirmField: 'Type your email address to confirm',
  confirmError: 'Type the address you sign in with.',
  confirm: 'Delete my account for good',
  keep: 'Keep my account',
  deleted: 'Your account is deleted.',
  unreachable: `${COPY.unreachableTitle}. Try again.`,
} as const;

export const EXPORT_FILENAME = 'blackkite-export.json';

/** Hand a JSON value to the browser as a file download. */
function download(value: unknown, filename: string): void {
  const blob = new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.append(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** /account: who is signed in, export (GET /me/export) and delete (DELETE /me) with a confirm step (spec 10). Design review. */
export function Account() {
  const navigate = useNavigate();
  const me = useResource('me', (s) => api.me(s));
  const [exportStatus, setExportStatus] = useState<'idle' | 'busy' | 'done' | 'failed'>('idle');
  const [confirming, setConfirming] = useState(false);
  const [typed, setTyped] = useState('');
  const [confirmError, setConfirmError] = useState<string | undefined>();
  const [deleteFailed, setDeleteFailed] = useState(false);
  const [signOutFailed, setSignOutFailed] = useState(false);

  if (me.error?.kind === 'unauthorized') return <SignIn />;

  const exportData = async () => {
    setExportStatus('busy');
    try {
      download(await api.exportMe(), EXPORT_FILENAME);
      setExportStatus('done');
    } catch {
      setExportStatus('failed');
    }
  };

  const signOut = async () => {
    setSignOutFailed(false);
    try {
      await api.logout();
      clearApiCache();
      navigate('/sign-in', { replace: true });
    } catch {
      setSignOutFailed(true);
    }
  };

  const remove = async () => {
    if (typed.trim().toLowerCase() !== me.data?.email.toLowerCase()) {
      setConfirmError(ACCOUNT_COPY.confirmError);
      return;
    }
    setConfirmError(undefined);
    setDeleteFailed(false);
    try {
      await api.deleteMe();
      clearApiCache();
      navigate('/sign-in', { replace: true, state: { notice: ACCOUNT_COPY.deleted } });
    } catch {
      setDeleteFailed(true);
    }
  };

  return (
    <AppShell path="/account" title={ACCOUNT_COPY.title}>
      <LoadState loading={me.loading} error={me.data ? null : me.error} onRetry={me.reload} />
      {me.data && (
        <>
          <Card label={ACCOUNT_COPY.signedIn} gap={12}>
            <div className={styles.strong}>{me.data.email}</div>
            {me.data.name && <div className={styles.body}>{me.data.name}</div>}
            <div className={styles.actions}>
              <Button variant="secondary" onClick={signOut}>
                {ACCOUNT_COPY.signOut}
              </Button>
            </div>
            {signOutFailed && (
              <div role="status" className={styles.alertStatus}>
                {ACCOUNT_COPY.unreachable}
              </div>
            )}
          </Card>

          <Card label={ACCOUNT_COPY.exportLabel} gap={12}>
            <div className={styles.body}>{ACCOUNT_COPY.exportBody}</div>
            <div className={styles.actions}>
              <Button variant="secondary" onClick={exportData} disabled={exportStatus === 'busy'}>
                {ACCOUNT_COPY.export}
              </Button>
            </div>
            <div role="status" className={exportStatus === 'failed' ? styles.alertStatus : styles.status}>
              {exportStatus === 'done' ? ACCOUNT_COPY.exported : exportStatus === 'failed' ? ACCOUNT_COPY.unreachable : ''}
            </div>
          </Card>

          <Card label={ACCOUNT_COPY.deleteLabel} gap={12}>
            <div className={styles.body}>{ACCOUNT_COPY.deleteBody}</div>
            {confirming ? (
              <>
                <Field
                  className={styles.threshold}
                  label={ACCOUNT_COPY.confirmField}
                  type="email"
                  name="confirmEmail"
                  autoComplete="off"
                  value={typed}
                  onChange={(e) => setTyped(e.target.value)}
                  error={confirmError}
                />
                <div className={styles.actions}>
                  <Button onClick={remove}>{ACCOUNT_COPY.confirm}</Button>
                  <Button
                    variant="secondary"
                    onClick={() => {
                      setConfirming(false);
                      setTyped('');
                      setConfirmError(undefined);
                    }}
                  >
                    {ACCOUNT_COPY.keep}
                  </Button>
                </div>
                {deleteFailed && (
                  <div role="status" className={styles.alertStatus}>
                    {ACCOUNT_COPY.unreachable}
                  </div>
                )}
              </>
            ) : (
              <div className={styles.actions}>
                <Button variant="secondary" onClick={() => setConfirming(true)}>
                  {ACCOUNT_COPY.delete}
                </Button>
              </div>
            )}
          </Card>
        </>
      )}
    </AppShell>
  );
}
