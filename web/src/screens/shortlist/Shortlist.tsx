import { useNavigate } from 'react-router';
import { api } from '../../api/client';
import { useResource } from '../../api/useResource';
import { Button } from '../../components/Button/Button';
import { Card } from '../../components/Card/Card';
import { ITEM_COPY } from '../items/ItemEditor';
import { FeedRow } from '../../components/FeedRow/FeedRow';
import { StateCard } from '../../components/StateCard/StateCard';
import { isClosed, pillFor, sortClosingSoonest } from '../../lib/feed';
import { rowSubtitle } from '../../lib/subtitle';
import { useAppLink } from '../../lib/useAppLink';
import { useIsDesktop } from '../../lib/useIsDesktop';
import { LoadState } from '../common/LoadState';
import { rowId } from '../feed/focus';
import { ComingUp } from '../plans/ComingUp';
import { AppShell } from '../shell/AppShell';
import { SignIn } from '../SignIn';

export const SHORTLIST_COPY = {
  title: 'Shortlist',
  emptyTitle: 'Nothing on your shortlist yet',
  emptyBody: 'Save anything in the feed and it waits here, closing soonest first.',
  openFeed: 'Open the feed',
} as const;

export function shortlistSummary(n: number): string {
  if (n === 0) return 'Saved items and the ones you are acting on.';
  return `${n} ${n === 1 ? 'item' : 'items'} saved or in progress, closing soonest first.`;
}

/**
 * /shortlist: saved and acting items (GET /shortlist), in the feed's own rows.
 * Not on any board (design review).
 */
export function Shortlist() {
  const desktop = useIsDesktop();
  const link = useAppLink();
  const navigate = useNavigate();
  const res = useResource('shortlist', (s) => api.shortlist(s));
  if (res.error?.kind === 'unauthorized') return <SignIn />;
  const items = res.data ? sortClosingSoonest(res.data) : [];

  return (
    <AppShell path="/shortlist" title={SHORTLIST_COPY.title} summary={res.data ? shortlistSummary(items.length) : undefined}>
      <div>
        <Button variant="secondary" onClick={() => navigate('/items/new')}>
          {ITEM_COPY.add}
        </Button>
      </div>
      <LoadState loading={res.loading} refreshing={res.refreshing} error={res.error} onRetry={res.reload} />
      {res.data && items.length === 0 && (
        <Card gap={12} aria-label="Shortlist status">
          <StateCard
            kind="nothing-new"
            title={SHORTLIST_COPY.emptyTitle}
            body={SHORTLIST_COPY.emptyBody}
            action={{ label: SHORTLIST_COPY.openFeed, onClick: () => navigate('/') }}
          />
        </Card>
      )}
      {items.length > 0 && (
        <Card padding={desktop ? '8px' : '4px 12px'} aria-label="Shortlist">
          {items.map((item) => (
            <FeedRow
              key={item.id}
              layout={desktop ? 'list' : 'phone'}
              id={rowId(item.id)}
              stream={item.stream}
              title={item.title}
              subtitle={rowSubtitle(item, desktop ? 'desktop' : 'phone')}
              fit={item.fit}
              deadline={pillFor(item)}
              closed={isClosed(item)}
              {...link(`/o/${item.id}`)}
            />
          ))}
        </Card>
      )}
      {res.data && <ComingUp headingId="shortlist-coming-up" />}
    </AppShell>
  );
}
