import { useLocation, useNavigate } from 'react-router';
import { BackLink } from '../../components/BackLink/BackLink';
import { Button } from '../../components/Button/Button';
import { Card } from '../../components/Card/Card';
import { TextLink } from '../../components/TextLink/TextLink';
import { TrustPanel } from '../../components/TrustNote/TrustNote';
import { detailMeta } from '../../lib/feed';
import { httpUrl } from '../../lib/externalUrl';
import { useAppLink } from '../../lib/useAppLink';
import type { FeedModel } from './model';
import { HEADING } from './focus';
import { DetailTop, FitSection, hasFitSection, LiveDetail, LiveRegion, LiveStatus } from './parts';
import styles from './OpportunityPhone.module.css';

/** opportunity-phone.html: one opportunity, with a sticky action bar. Below 792 px. */
export function OpportunityPhone({ model, id }: { model: FeedModel; id: string }) {
  const link = useAppLink();
  const navigate = useNavigate();
  const { search } = useLocation();
  const item = model.byId(id);
  const back = link('/');

  if (!item) {
    return (
      <div className={styles.page}>
        <header className={styles.header}>
          <BackLink {...back}>Feed</BackLink>
        </header>
        <main className={styles.content}>
          <h1 className={styles.h1}>We could not find that item</h1>
          <div className={styles.meta}>It may have been removed at the source.</div>
        </main>
      </div>
    );
  }

  const saved = model.saved.has(item.id);
  // Only http(s) links to the original notice; anything else renders no link.
  const original = httpUrl(item.detail.originalUrl);
  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <BackLink {...back}>Feed</BackLink>
      </header>

      <main className={styles.content}>
        {model.live?.failed && <LiveStatus model={{ ...model, live: { ...model.live, status: {} } }} />}
        <DetailTop item={item} tagGap={6} />
        <div className={styles.titleBlock}>
          <h1 className={styles.h1}>{item.title}</h1>
          <div className={styles.meta}>{detailMeta(item)}</div>
        </div>
        {hasFitSection(item) && (
          <Card padding="16px" gap={10}>
            <FitSection item={item} />
          </Card>
        )}
        <TrustPanel state={item.detail.trust.state} tone="stone">
          {item.detail.trust.phone}
        </TrustPanel>
        {original && (
          <TextLink spacing="block" href={original} target="_blank" rel="noopener noreferrer">
            Read the original notice
          </TextLink>
        )}
        {model.live && <LiveDetail key={item.id} model={model} item={item} />}
      </main>

      <div className={styles.actions} role="group" aria-label="Actions">
        <Button size="large" aria-pressed={saved} onClick={() => model.toggleSaved(item.id)}>
          Save to shortlist
        </Button>
        <Button
          size="large"
          variant="secondary"
          onClick={() => {
            // Back on the feed, focus lands on the row that followed this one (or the heading).
            const rows = model.items.filter((i) => !i.hideOnPhone);
            const index = rows.indexOf(item);
            const next = rows[index + 1] ?? rows[index - 1];
            model.dismiss(item.id);
            navigate(`/${search}`, { state: { focusRow: next && next !== item ? next.id : HEADING } });
          }}
        >
          Not for me
        </Button>
      </div>
      <LiveRegion message={model.announcement} />
    </div>
  );
}
