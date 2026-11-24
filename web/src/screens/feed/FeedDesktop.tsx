import { useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router';
import { Button } from '../../components/Button/Button';
import { Card } from '../../components/Card/Card';
import { FeedRow } from '../../components/FeedRow/FeedRow';
import { Kite } from '../../components/Kite/Kite';
import { KiteOrbit } from '../../components/KiteOrbit/KiteOrbit';
import { NavItem } from '../../components/NavItem/NavItem';
import { StateCard } from '../../components/StateCard/StateCard';
import { TextLink } from '../../components/TextLink/TextLink';
import { TrustPanel } from '../../components/TrustNote/TrustNote';
import { Wordmark } from '../../components/Wordmark/Wordmark';
import type { FeedItem } from '../../fixtures/types';
import { detailMeta, feedSummary, greeting, isClosed, nextDigest, pillFor } from '../../lib/feed';
import { rowSubtitle } from '../../lib/subtitle';
import { useAppLink } from '../../lib/useAppLink';
import type { FeedModel } from './model';
import { DetailTop, FilterChips, FitSection, hasFitSection, LiveRegion } from './parts';
import { useFeedKeys } from './useFeedKeys';
import { useStateCard } from './useStateCard';
import styles from './FeedDesktop.module.css';

export const rowId = (id: string) => `row-${id}`;

export const NAV = [
  { label: 'Feed', to: '/' },
  { label: 'Shortlist', to: '/shortlist' },
  { label: 'Calendar', to: '/calendar' },
  { label: 'Sources', to: '/sources' },
  { label: 'Profiles', to: '/profiles' },
] as const;

/** feed-desktop.html: sidebar, greeting, filters, the list and the detail pane. Fluid from 792 px up. */
export function FeedDesktop({ model, openId }: { model: FeedModel; openId: string | null }) {
  const link = useAppLink();
  const navigate = useNavigate();
  const { search } = useLocation();
  const { feed } = model.fixture;
  const items = model.items;

  // The open item; a filtered-out or dismissed one falls back to the first in the list.
  const requested = openId ? model.byId(openId) : undefined;
  const selected: FeedItem | undefined =
    requested && items.includes(requested) ? requested : openId && !requested ? undefined : items[0];
  const notFound = openId !== null && !requested;

  const select = (id: string, replace = true) => navigate(`/o/${id}${search}`, { replace });

  const dismissSelected = () => {
    if (!selected) return;
    const index = items.indexOf(selected);
    const next = items[index + 1] ?? items[index - 1];
    model.dismiss(selected.id);
    if (next) select(next.id);
    else navigate(`/${search}`, { replace: true });
  };

  useFeedKeys({
    onNext: () => {
      const i = selected ? items.indexOf(selected) : -1;
      const next = items[Math.min(i + 1, items.length - 1)];
      if (next && next !== selected) select(next.id);
    },
    onPrevious: () => {
      const i = selected ? items.indexOf(selected) : 0;
      const prev = items[Math.max(i - 1, 0)];
      if (prev && prev !== selected) select(prev.id);
    },
    onSave: () => selected && model.toggleSaved(selected.id),
    onDismiss: dismissSelected,
  });

  // Keep the selected row in view as J and K move through a long list.
  useEffect(() => {
    const row = selected && document.getElementById(rowId(selected.id));
    row?.scrollIntoView?.({ block: 'nearest' });
  }, [selected]);

  const showList = model.state !== 'nothing-new' && items.length > 0;
  const stateCard = useStateCard(model);

  return (
    <div className={styles.page}>
      <nav aria-label="Main" className={styles.nav}>
        <div className={styles.lockup}>
          <Kite label="Blackkite" width={42} height={28} rotate={-16} />
          <Wordmark size={22} />
        </div>
        <div className={styles.navList}>
          {NAV.map((n) => (
            <NavItem key={n.to} variant="side" current={n.to === '/'} {...link(n.to)}>
              {n.label}
            </NavItem>
          ))}
        </div>
        <div className={styles.digest}>
          <div className={styles.digestLabel}>Next digest</div>
          <div>{nextDigest(feed.digest.channel)}</div>
        </div>
      </nav>

      <main className={styles.main}>
        <div className={styles.head}>
          <div className={styles.greet}>
            <h1 className={styles.h1}>{greeting(feed.user.name)}</h1>
            <div className={styles.summary}>{feedSummary(items)}</div>
          </div>
          <div className={styles.checked}>
            <KiteOrbit />
            <span>{`${feed.sources.checked} sources checked ${feed.sources.when}`}</span>
          </div>
        </div>

        <div className={styles.toolbar}>
          <FilterChips model={model} className={styles.chips} />
          <div className={styles.sort}>Closing soonest first</div>
        </div>

        <div className={styles.grid}>
          <div className={styles.column}>
            {stateCard && (
              <Card gap={12} aria-label="Feed status">
                <StateCard {...stateCard} />
              </Card>
            )}
            {showList && (
              <Card padding="8px" aria-label="Opportunities">
                <div className={styles.rows}>
                  {items.map((item) => (
                    <FeedRow
                      key={item.id}
                      layout="list"
                      id={rowId(item.id)}
                      stream={item.stream}
                      title={item.title}
                      subtitle={rowSubtitle(item, 'desktop')}
                      fit={item.fit}
                      deadline={pillFor(item)}
                      closed={isClosed(item)}
                      isNew={item.isNew}
                      selected={item === selected}
                      {...link(`/o/${item.id}`)}
                    />
                  ))}
                </div>
                <div className={styles.hint}>J and K to move · S to save · X for not for me</div>
              </Card>
            )}
          </div>

          {showList && selected && <DetailPane item={selected} model={model} onDismiss={dismissSelected} />}
          {notFound && (
            <Card as="article" padding="24px" gap={16} aria-label="Not found">
              <div className={styles.summary}>We could not find that item. It may have been removed at the source.</div>
            </Card>
          )}
        </div>
      </main>
      <LiveRegion message={model.announcement} />
    </div>
  );
}

function DetailPane({ item, model, onDismiss }: { item: FeedItem; model: FeedModel; onDismiss: () => void }) {
  const saved = model.saved.has(item.id);
  const headingId = `detail-${item.id}`;
  return (
    <Card as="article" padding="24px" gap={16} aria-labelledby={headingId}>
      <DetailTop item={item} tagGap={8} />
      <div className={styles.titleBlock}>
        <h2 id={headingId} className={styles.h2}>
          {item.title}
        </h2>
        <div className={styles.meta}>{detailMeta(item)}</div>
      </div>
      {hasFitSection(item) && (
        <div className={styles.fit}>
          <FitSection item={item} />
        </div>
      )}
      <TrustPanel state={item.detail.trust.state} tone="mist">
        {item.detail.trust.desktop}
      </TrustPanel>
      <div className={styles.actions}>
        <Button aria-pressed={saved} onClick={() => model.toggleSaved(item.id)}>
          Save to shortlist
        </Button>
        <Button variant="secondary" onClick={onDismiss}>
          Not for me
        </Button>
        <TextLink href={item.detail.originalUrl} target="_blank" rel="noopener noreferrer">
          Read the original
        </TextLink>
      </div>
    </Card>
  );
}
