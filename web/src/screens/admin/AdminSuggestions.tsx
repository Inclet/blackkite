import { useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router';
import { ApiError } from '../../api/client';
import { sourcesApi, type Suggestion } from '../../api/sources';
import { primeCache, useResource } from '../../api/useResource';
import { Button } from '../../components/Button/Button';
import { Card } from '../../components/Card/Card';
import { COPY } from '../common/copy';
import { LoadState } from '../common/LoadState';
import { AppShell } from '../shell/AppShell';
import styles from '../sources/Sources.module.css';
import { formatDay } from '../sources/words';
import { adminFailure, AdminOnly, BackToAdmin } from './AdminOnly';

export const SUGGESTIONS_COPY = {
  title: 'Suggestions',
  summary: 'Sources members have suggested. Accept one to create a source from it, or reject it.',
  waiting: 'Waiting for review',
  accepted: 'Accepted, no source yet',
  none: 'No suggestions are waiting.',
  sent: (when: string) => `Suggested ${when}`,
  accept: 'Accept',
  reject: 'Reject',
  create: 'Create source from this',
  didAccept: (url: string) => `Accepted ${url}. Create the source when you are ready.`,
  didReject: (url: string) => `Rejected ${url}.`,
  already: 'Someone already reviewed this suggestion. The list is up to date now.',
  unreachable: `${COPY.unreachableTitle}. Nothing changed; try again.`,
} as const;

/** /admin/suggestions: the member suggestion queue (spec 4.3). Design review. */
export function AdminSuggestions() {
  return (
    <AdminOnly path="/admin/suggestions" title={SUGGESTIONS_COPY.title}>
      <Queue />
    </AdminOnly>
  );
}

function Queue() {
  const navigate = useNavigate();
  const waiting = useResource('admin-suggestions', (s) => sourcesApi.adminSuggestions('suggested', s));
  const accepted = useResource('admin-suggestions-accepted', (s) => sourcesApi.adminSuggestions('accepted', s));
  const [message, setMessage] = useState<{ text: string; alert: boolean } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const failed = adminFailure('/admin/suggestions', waiting.error, accepted.error);
  if (failed) return failed;

  const review = async (s: Suggestion, decision: 'accept' | 'reject') => {
    setBusy(s.id);
    setMessage(null);
    try {
      const done = await (decision === 'accept' ? sourcesApi.acceptSuggestion(s.id) : sourcesApi.rejectSuggestion(s.id));
      waiting.setData((list) => list?.filter((x) => x.id !== s.id));
      if (decision === 'accept') accepted.setData((list) => [...(list ?? []), { ...s, ...done }]);
      setMessage({ text: decision === 'accept' ? SUGGESTIONS_COPY.didAccept(s.url) : SUGGESTIONS_COPY.didReject(s.url), alert: false });
    } catch (err) {
      if (err instanceof ApiError && err.kind === 'conflict') {
        setMessage({ text: SUGGESTIONS_COPY.already, alert: true });
        waiting.reload();
        accepted.reload();
      } else setMessage({ text: SUGGESTIONS_COPY.unreachable, alert: true });
    } finally {
      setBusy(null);
    }
  };

  const create = (s: Suggestion) => {
    primeCache('admin-suggestions-accepted', accepted.data);
    navigate(`/admin/sources/new?suggestion=${encodeURIComponent(s.id)}`);
  };

  const unused = (accepted.data ?? []).filter((s) => !s.sourceId);
  return (
    <AppShell path="/admin/suggestions" title={SUGGESTIONS_COPY.title} summary={SUGGESTIONS_COPY.summary}>
      <BackToAdmin />
      <LoadState loading={waiting.loading || accepted.loading} error={waiting.error ?? accepted.error} onRetry={() => (waiting.reload(), accepted.reload())} />
      <div role="status" className={message?.alert ? styles.alertStatus : styles.status}>
        {message?.text ?? ''}
      </div>
      {unused.length > 0 && (
        <Card label={SUGGESTIONS_COPY.accepted} padding="22px 24px 12px" gap={4} aria-label={SUGGESTIONS_COPY.accepted}>
          <div className={styles.rows}>
            {unused.map((s) => (
              <Row key={s.id} suggestion={s}>
                <Button onClick={() => create(s)} aria-label={`${SUGGESTIONS_COPY.create}: ${s.url}`}>
                  {SUGGESTIONS_COPY.create}
                </Button>
              </Row>
            ))}
          </div>
        </Card>
      )}
      {waiting.data && (
        <Card label={SUGGESTIONS_COPY.waiting} padding="22px 24px 12px" gap={4} aria-label={SUGGESTIONS_COPY.waiting}>
          {waiting.data.length === 0 ? (
            <div className={styles.status} style={{ paddingBottom: 10 }}>
              {SUGGESTIONS_COPY.none}
            </div>
          ) : (
            <div className={styles.rows}>
              {waiting.data.map((s) => (
                <Row key={s.id} suggestion={s}>
                  <Button disabled={busy === s.id} onClick={() => void review(s, 'accept')} aria-label={`${SUGGESTIONS_COPY.accept} ${s.url}`}>
                    {SUGGESTIONS_COPY.accept}
                  </Button>
                  <Button variant="secondary" disabled={busy === s.id} onClick={() => void review(s, 'reject')} aria-label={`${SUGGESTIONS_COPY.reject} ${s.url}`}>
                    {SUGGESTIONS_COPY.reject}
                  </Button>
                </Row>
              ))}
            </div>
          )}
        </Card>
      )}
    </AppShell>
  );
}

function Row({ suggestion: s, children }: { suggestion: Suggestion; children: ReactNode }) {
  return (
    <div className={styles.stackRow}>
      <div className={styles.rowText}>
        <span className={styles.rowTitle}>{s.url}</span>
        <span className={styles.meta}>{SUGGESTIONS_COPY.sent(formatDay(s.createdAt))}</span>
      </div>
      {s.note && <div className={styles.note}>{s.note}</div>}
      <div className={styles.actions}>{children}</div>
    </div>
  );
}
