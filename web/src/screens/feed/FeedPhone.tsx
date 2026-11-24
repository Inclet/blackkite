import { AccountButton } from '../../components/AccountButton/AccountButton';
import { Card } from '../../components/Card/Card';
import { FeedRow } from '../../components/FeedRow/FeedRow';
import { Kite } from '../../components/Kite/Kite';
import { NavItem } from '../../components/NavItem/NavItem';
import { StateCard } from '../../components/StateCard/StateCard';
import { Wordmark } from '../../components/Wordmark/Wordmark';
import { feedSummary, greeting, isClosed, pillFor } from '../../lib/feed';
import { rowSubtitle } from '../../lib/subtitle';
import { useAppLink } from '../../lib/useAppLink';
import type { FeedModel } from './model';
import { FilterChips, LiveRegion } from './parts';
import { useStateCard } from './useStateCard';
import styles from './FeedPhone.module.css';

export const TABS = [
  { label: 'Feed', to: '/' },
  { label: 'Shortlist', to: '/shortlist' },
  { label: 'Calendar', to: '/calendar' },
  { label: 'More', to: '/more' },
] as const;

/** feed-phone.html: header, greeting, scrolling chips, the list and the tab bar. Below 792 px (decision 6). */
export function FeedPhone({ model }: { model: FeedModel }) {
  const link = useAppLink();
  const { feed } = model.fixture;
  // The summary counts the whole feed, as on the board (which omits a row on the phone, decision 4).
  const rows = model.items.filter((i) => !i.hideOnPhone);
  const stateCard = useStateCard(model);
  const showList = model.state !== 'nothing-new' && rows.length > 0;
  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.lockup}>
          <Kite label="Blackkite" width={39} height={26} rotate={-16} />
          <Wordmark size={20} />
        </div>
        <AccountButton name={feed.user.name} />
      </header>

      <main className={styles.main}>
        <div className={styles.greet}>
          <h1 className={styles.h1}>{greeting(feed.user.name)}</h1>
          <div className={styles.summary}>{feedSummary(model.items)}</div>
        </div>

        <FilterChips model={model} className={styles.chips} chipClassName={styles.chip} />

        {stateCard && (
          <Card className={styles.card} padding="22px 24px" gap={12} aria-label="Feed status">
            <StateCard {...stateCard} />
          </Card>
        )}
        {showList && (
          <Card className={styles.card} padding="4px 12px" aria-label="Opportunities">
            {rows.map((item) => (
              <FeedRow
                key={item.id}
                layout="phone"
                stream={item.stream}
                title={item.title}
                subtitle={rowSubtitle(item, 'phone')}
                fit={item.fit}
                deadline={pillFor(item)}
                closed={isClosed(item)}
                isNew={item.isNew}
                {...link(`/o/${item.id}`)}
              />
            ))}
          </Card>
        )}
      </main>

      <nav aria-label="Main" className={styles.tabs}>
        {TABS.map((t) => (
          <NavItem key={t.to} variant="tab" current={t.to === '/'} {...link(t.to)}>
            {t.label}
          </NavItem>
        ))}
      </nav>
      <LiveRegion message={model.announcement} />
    </div>
  );
}
