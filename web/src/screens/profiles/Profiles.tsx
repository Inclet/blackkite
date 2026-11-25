import { useLocation, useNavigate } from 'react-router';
import { api } from '../../api/client';
import type { Profile } from '../../api/types';
import { useResource } from '../../api/useResource';
import { Button } from '../../components/Button/Button';
import { Card } from '../../components/Card/Card';
import { StateCard } from '../../components/StateCard/StateCard';
import { Tag } from '../../components/Tag/Tag';
import { TextLink } from '../../components/TextLink/TextLink';
import { STREAM_PLURALS } from '../../lib/streams';
import { useAppLink } from '../../lib/useAppLink';
import { LoadState } from '../common/LoadState';
import { AppShell } from '../shell/AppShell';
import { SignIn } from '../SignIn';
import styles from './Profiles.module.css';

export const PROFILES_COPY = {
  title: 'Profiles',
  summary: 'Blackkite ranks every item against each profile and shows the best fit.',
  emptyTitle: 'Tell Blackkite what you do',
  emptyBody: 'Add a profile for a business or for your own interests. Until then you see everything, unranked.',
  addBusiness: 'Add a business profile',
  addPersonal: 'Add a personal profile',
  edit: 'Edit',
  paused: 'Paused',
  provisional: 'Provisional',
} as const;

export function profileMeta(p: Profile): string {
  const kind = p.type === 'business' ? 'Business' : 'Personal';
  const streams = (p.data.streams ?? []).map((s) => STREAM_PLURALS[s]);
  return [kind, streams.join(', ')].filter(Boolean).join(' · ');
}

/** /profiles: the caller's profiles, and the way to add one. Not on any board (design review). */
export function Profiles() {
  const link = useAppLink();
  const navigate = useNavigate();
  const { state } = useLocation();
  const res = useResource('profiles', (s) => api.profiles(s));
  if (res.error?.kind === 'unauthorized') return <SignIn />;
  const profiles = res.data ?? [];
  const notice = (state as { notice?: string } | null)?.notice;

  return (
    <AppShell path="/profiles" title={PROFILES_COPY.title} summary={PROFILES_COPY.summary}>
      <LoadState loading={res.loading} error={res.error} onRetry={res.reload} />
      {notice && (
        <div role="status" className={styles.status}>
          {notice}
        </div>
      )}
      {res.data && profiles.length === 0 && (
        <Card gap={12} aria-label="Profiles status">
          <StateCard kind="first-visit" title={PROFILES_COPY.emptyTitle} body={PROFILES_COPY.emptyBody} />
        </Card>
      )}
      {profiles.length > 0 && (
        <Card padding="12px 24px" aria-label="Your profiles">
          <div className={styles.rows}>
            {profiles.map((p) => (
              <div key={p.id} className={styles.row}>
                <div className={styles.rowText}>
                  <span className={styles.rowTitle}>{p.name}</span>
                  <span className={styles.meta}>{profileMeta(p)}</span>
                </div>
                <div className={styles.actions}>
                  {p.data.provisional && <Tag kind="profile">{PROFILES_COPY.provisional}</Tag>}
                  {!p.active && <Tag kind="profile">{PROFILES_COPY.paused}</Tag>}
                  <TextLink {...link(`/profiles/${encodeURIComponent(p.id)}`)} aria-label={`${PROFILES_COPY.edit} ${p.name}`}>
                    {PROFILES_COPY.edit}
                  </TextLink>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}
      {res.data && (
        <div className={styles.actions}>
          <Button onClick={() => navigate('/profiles/new/business')}>{PROFILES_COPY.addBusiness}</Button>
          <Button variant="secondary" onClick={() => navigate('/profiles/new/personal')}>
            {PROFILES_COPY.addPersonal}
          </Button>
        </div>
      )}
    </AppShell>
  );
}
