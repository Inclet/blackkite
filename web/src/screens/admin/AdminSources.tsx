import { useNavigate } from 'react-router';
import { sourcesApi, type AdminSource } from '../../api/sources';
import { useResource } from '../../api/useResource';
import { Button } from '../../components/Button/Button';
import { Card } from '../../components/Card/Card';
import { StateCard } from '../../components/StateCard/StateCard';
import { Tag } from '../../components/Tag/Tag';
import { TextLink } from '../../components/TextLink/TextLink';
import { useAppLink } from '../../lib/useAppLink';
import { LoadState } from '../common/LoadState';
import { AppShell } from '../shell/AppShell';
import styles from '../sources/Sources.module.css';
import {
  COLLECTOR_WORDS,
  formatWhen,
  HEALTH_WORDS,
  itemsCount,
  KIND_WORDS,
  STATUS_HELP,
  STATUS_ORDER,
  sourceGate,
  STATUS_WORDS,
  streamList,
} from '../sources/words';
import { adminFailure, AdminOnly, BackToAdmin } from './AdminOnly';

export const ADMIN_SOURCES_COPY = {
  title: 'Sources',
  summary: 'Every source, by status. New sources start in testing; their items stay hidden from members until you make them active.',
  add: 'Add a source',
  edit: 'Edit',
  lastRun: (when: string) => `Last run ${when}`,
  neverRun: 'Never run',
  health: (word: string) => `Health: ${word}`,
  emptyTitle: 'No sources yet',
  emptyBody: 'Add the first one. A test run shows what it finds before anything is saved.',
} as const;

/** /admin/sources: the registry grouped by status, with health and last run. Design review. */
export function AdminSources() {
  return (
    <AdminOnly path="/admin/sources" title={ADMIN_SOURCES_COPY.title}>
      <List />
    </AdminOnly>
  );
}

function List() {
  const navigate = useNavigate();
  const res = useResource('admin-sources', (s) => sourcesApi.adminSources(s));
  const failed = adminFailure('/admin/sources', res.error);
  if (failed) return failed;
  const all = res.data ?? [];
  return (
    <AppShell path="/admin/sources" title={ADMIN_SOURCES_COPY.title} summary={ADMIN_SOURCES_COPY.summary}>
      <BackToAdmin />
      <LoadState loading={res.loading} error={res.error} onRetry={res.reload} />
      {res.data && (
        <div className={styles.actions}>
          <Button onClick={() => navigate('/admin/sources/new')}>{ADMIN_SOURCES_COPY.add}</Button>
        </div>
      )}
      {res.data && all.length === 0 && (
        <Card gap={12} aria-label="Sources status">
          <StateCard kind="first-visit" title={ADMIN_SOURCES_COPY.emptyTitle} body={ADMIN_SOURCES_COPY.emptyBody} />
        </Card>
      )}
      {STATUS_ORDER.map((status) => {
        const group = all.filter((s) => s.status === status);
        if (!group.length) return null;
        const label = `${STATUS_WORDS[status]} (${group.length})`;
        return (
          <Card key={status} label={label} padding="22px 24px 12px" gap={4} aria-label={STATUS_WORDS[status]}>
            <div className={styles.status}>{STATUS_HELP[status]}</div>
            <div className={styles.rows}>
              {group.map((s) => (
                <Row key={s.id} source={s} />
              ))}
            </div>
          </Card>
        );
      })}
    </AppShell>
  );
}

function Row({ source: s }: { source: AdminSource }) {
  const link = useAppLink();
  const about = [s.publisher, KIND_WORDS[s.kind] ?? s.kind, streamList(s.streams), COLLECTOR_WORDS[s.collectorType] ?? s.collectorType]
    .filter(Boolean)
    .join(' · ');
  const runs = [s.lastRunAt ? ADMIN_SOURCES_COPY.lastRun(formatWhen(s.lastRunAt)) : ADMIN_SOURCES_COPY.neverRun, itemsCount(s.items30d)].join(' · ');
  return (
    <div className={styles.row}>
      <div className={styles.rowText}>
        <span className={styles.rowTitle}>{s.name}</span>
        <span className={styles.meta}>{about}</span>
        <span className={styles.meta}>{runs}</span>
        {(s.status === 'testing' || s.status === 'paused') && <span className={styles.meta}>{sourceGate(s)}</span>}
      </div>
      <div className={styles.side}>
        <Tag kind="profile">{ADMIN_SOURCES_COPY.health(HEALTH_WORDS[s.health])}</Tag>
        <TextLink {...link(`/admin/sources/${encodeURIComponent(s.id)}`)} aria-label={`${ADMIN_SOURCES_COPY.edit} ${s.name}`}>
          {ADMIN_SOURCES_COPY.edit}
        </TextLink>
      </div>
    </div>
  );
}
