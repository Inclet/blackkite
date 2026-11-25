import { useState } from 'react';
import { sourcesApi, type CatalogueItem } from '../../api/sources';
import { useResource } from '../../api/useResource';
import { Button } from '../../components/Button/Button';
import { Card } from '../../components/Card/Card';
import { Tag } from '../../components/Tag/Tag';
import { TrustNote } from '../../components/TrustNote/TrustNote';
import { formatShortDate } from '../../lib/deadline';
import { COPY } from '../common/copy';
import { LoadState } from '../common/LoadState';
import { AppShell } from '../shell/AppShell';
import styles from '../sources/Sources.module.css';
import { STATUS_WORDS } from '../sources/words';
import { adminFailure, AdminOnly, BackToAdmin } from './AdminOnly';

export const REVIEW_COPY = {
  title: 'Review',
  summary: 'Items Blackkite flagged for a person to check, with the reasons. Mark one reviewed once you have checked it.',
  none: 'Nothing needs review.',
  more: (shown: number, total: number) => `Showing ${shown} of ${total}.`,
  reasons: 'Why it was flagged',
  noReason: 'No reason was recorded.',
  sources: 'Sources',
  original: 'original',
  visible: 'Members can see it.',
  hidden: 'Only admins see it: no active source carries it yet.',
  deadline: (d: string) => `Closes ${formatShortDate(d)}`,
  mark: 'Mark reviewed',
  marked: (title: string) => `Marked reviewed: ${title}.`,
  unreachable: `${COPY.unreachableTitle}. It was not marked; try again.`,
} as const;

/** /admin/review: needs_review items and their reasons (spec 3, 5.6). Design review. */
export function AdminReview() {
  return (
    <AdminOnly path="/admin/review" title={REVIEW_COPY.title}>
      <Queue />
    </AdminOnly>
  );
}

function Queue() {
  const res = useResource('admin-review', (s) => sourcesApi.reviewQueue(s));
  const [message, setMessage] = useState<{ text: string; alert: boolean } | null>(null);
  const failed = adminFailure('/admin/review', res.error);
  if (failed) return failed;

  const mark = async (item: CatalogueItem) => {
    setMessage(null);
    try {
      await sourcesApi.markReviewed(item.id);
      res.setData((page) => page && { total: Math.max(0, page.total - 1), items: page.items.filter((i) => i.id !== item.id) });
      setMessage({ text: REVIEW_COPY.marked(item.title), alert: false });
    } catch {
      setMessage({ text: REVIEW_COPY.unreachable, alert: true });
    }
  };

  const items = res.data?.items.filter((i) => i.needsReview) ?? [];
  return (
    <AppShell path="/admin/review" title={REVIEW_COPY.title} summary={REVIEW_COPY.summary}>
      <BackToAdmin />
      <LoadState loading={res.loading} error={res.error} onRetry={res.reload} />
      <div role="status" className={message?.alert ? styles.alertStatus : styles.status}>
        {message?.text ?? ''}
      </div>
      {res.data && items.length === 0 && (
        <Card aria-label="Review status">
          <div className={styles.status}>{REVIEW_COPY.none}</div>
        </Card>
      )}
      {items.map((item) => (
        <Card key={item.id} gap={10} aria-label={item.title}>
          <div className={styles.side}>
            <Tag kind="stream" stream={item.stream} icon />
            {item.deadline && <Tag kind="profile">{REVIEW_COPY.deadline(item.deadline)}</Tag>}
          </div>
          <div className={styles.rowText}>
            <span className={styles.rowTitle}>{item.title}</span>
            {item.organisation && <span className={styles.meta}>{item.organisation}</span>}
          </div>
          <TrustNote state={item.trust} />
          <div className={styles.groupLabel}>{REVIEW_COPY.reasons}</div>
          {item.reviewReasons.length ? (
            <ul className={styles.list}>
              {item.reviewReasons.map((r, i) => (
                <li key={`${r.code}-${i}`}>{r.detail || r.code}</li>
              ))}
            </ul>
          ) : (
            <div className={styles.status}>{REVIEW_COPY.noReason}</div>
          )}
          <div className={styles.groupLabel}>{REVIEW_COPY.sources}</div>
          <ul className={styles.list}>
            {item.sources.map((s, i) => (
              <li key={`${s.name}-${i}`}>
                {s.name} ({[STATUS_WORDS[s.status as keyof typeof STATUS_WORDS] ?? s.status, s.isOriginal ? REVIEW_COPY.original : null].filter(Boolean).join(', ')})
              </li>
            ))}
          </ul>
          <div className={styles.status}>{item.memberVisible ? REVIEW_COPY.visible : REVIEW_COPY.hidden}</div>
          <div className={styles.actions}>
            <Button onClick={() => void mark(item)} aria-label={`${REVIEW_COPY.mark}: ${item.title}`}>
              {REVIEW_COPY.mark}
            </Button>
          </div>
        </Card>
      ))}
      {res.data && res.data.total > items.length && items.length > 0 && <div className={styles.status}>{REVIEW_COPY.more(items.length, res.data.total)}</div>}
    </AppShell>
  );
}
