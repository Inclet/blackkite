import { useState } from 'react';
import { ApiError } from '../../api/client';
import { m4Api, type ShareableItem } from '../../api/m4';
import { useResource } from '../../api/useResource';
import { Button } from '../../components/Button/Button';
import { Card } from '../../components/Card/Card';
import { Tag } from '../../components/Tag/Tag';
import { formatFullDate } from '../../lib/detailWords';
import { COPY } from '../common/copy';
import { LoadState } from '../common/LoadState';
import { AppShell } from '../shell/AppShell';
import styles from '../sources/Sources.module.css';
import { adminFailure, AdminOnly, BackToAdmin } from './AdminOnly';

/** Not on any board (design review). */
export const SHAREABLE_COPY = {
  title: 'Shareable private items',
  summary: 'Items members added for themselves and said an admin may make public. Publishing shows the item to every member; the owner’s notes and progress stay private.',
  none: 'No private items are waiting to be made public.',
  date: (d: string) => `Date ${formatFullDate(d)}`,
  agreed: (d: string) => `The owner agreed to share it on ${formatFullDate(d)}.`,
  publish: 'Make public',
  published: (title: string) => `Made public: ${title}.`,
  noConsent: 'The owner no longer allows this, so it stays private.',
  unreachable: `${COPY.unreachableTitle}. Nothing changed; try again.`,
} as const;

/** /admin/shareable: private items with the owner's consent, and "Make public" (contract section 5). */
export function AdminShareable() {
  return (
    <AdminOnly path="/admin/shareable" title={SHAREABLE_COPY.title}>
      <Queue />
    </AdminOnly>
  );
}

function Queue() {
  const res = useResource('admin-shareable', (s) => m4Api.shareable(s));
  const [message, setMessage] = useState<{ text: string; alert: boolean } | null>(null);
  const failed = adminFailure('/admin/shareable', res.error);
  if (failed) return failed;

  const drop = (item: ShareableItem) => res.setData((page) => page && { total: Math.max(0, page.total - 1), items: page.items.filter((i) => i.id !== item.id) });

  const publish = async (item: ShareableItem) => {
    setMessage(null);
    try {
      await m4Api.publish(item.id);
      drop(item);
      setMessage({ text: SHAREABLE_COPY.published(item.title), alert: false });
    } catch (e) {
      if (e instanceof ApiError && (e.kind === 'conflict' || e.kind === 'not-found')) {
        drop(item);
        setMessage({ text: `${item.title}: ${SHAREABLE_COPY.noConsent}`, alert: true });
      } else setMessage({ text: SHAREABLE_COPY.unreachable, alert: true });
    }
  };

  const items = res.data?.items ?? [];
  return (
    <AppShell path="/admin/shareable" title={SHAREABLE_COPY.title} summary={SHAREABLE_COPY.summary}>
      <BackToAdmin />
      <LoadState loading={res.loading} error={res.error} onRetry={res.reload} />
      <div role="status" className={message?.alert ? styles.alertStatus : styles.status}>
        {message?.text ?? ''}
      </div>
      {res.data && items.length === 0 && (
        <Card aria-label="Shareable items status">
          <div className={styles.status}>{SHAREABLE_COPY.none}</div>
        </Card>
      )}
      {items.map((item) => (
        <Card key={item.id} gap={10} aria-label={item.title}>
          <div className={styles.side}>
            <Tag kind="stream" stream={item.stream} icon />
            {item.deadline && <Tag kind="profile">{SHAREABLE_COPY.date(item.deadline)}</Tag>}
          </div>
          <div className={styles.rowText}>
            <span className={styles.rowTitle}>{item.title}</span>
            {item.organisation && <span className={styles.meta}>{item.organisation}</span>}
            {item.shareConsentAt && <span className={styles.meta}>{SHAREABLE_COPY.agreed(item.shareConsentAt)}</span>}
          </div>
          <div className={styles.actions}>
            <Button onClick={() => void publish(item)} aria-label={`${SHAREABLE_COPY.publish}: ${item.title}`}>
              {SHAREABLE_COPY.publish}
            </Button>
          </div>
        </Card>
      ))}
    </AppShell>
  );
}
