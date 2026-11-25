import { useEffect, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router';
import { Button } from '../../components/Button/Button';
import { Card } from '../../components/Card/Card';
import { FeedRow } from '../../components/FeedRow/FeedRow';
import { KiteOrbit } from '../../components/KiteOrbit/KiteOrbit';
import { StateCard } from '../../components/StateCard/StateCard';
import { TextLink } from '../../components/TextLink/TextLink';
import { TrustPanel } from '../../components/TrustNote/TrustNote';
import type { FeedItem } from '../../fixtures/types';
import { detailMeta, feedSummary, greeting, isClosed, pillFor } from '../../lib/feed';
import { rowSubtitle } from '../../lib/subtitle';
import { httpUrl } from '../../lib/externalUrl';
import { useAppLink } from '../../lib/useAppLink';
import { Sidebar } from '../shell/Sidebar';
import { DISMISS_NAV, type FeedModel } from './model';
import { DetailTop, DismissReasonPrompt, FilterChips, FitSection, hasFitSection, LiveDetail, LiveRegion, LiveStatus, SaveButton } from './parts';
import { HEADING, rowId } from './focus';
import { useLiveList, useLiveSelection } from './liveList';
import { useFeedKeys } from './useFeedKeys';
import { useStateCard } from './useStateCard';
import styles from './FeedDesktop.module.css';

/** feed-desktop.html: sidebar, greeting, filters, the list and the detail pane. Fluid from 792 px up. */
export function FeedDesktop({ model, openId }: { model: FeedModel; openId: string | null }) {
  const link = useAppLink();
  const navigate = useNavigate();
  const location = useLocation();
  const { search } = location;
  const { feed } = model;
  const items = model.items;

  // The open item; a filtered-out or dismissed one falls back to the first in the list.
  const requested = openId ? model.byId(openId) : undefined;
  const selected: FeedItem | undefined =
    requested && items.includes(requested) ? requested : openId && !requested ? undefined : items[0];
  const notFound = openId !== null && !requested;

  // Keys read the list and selection from here, not from this render: a key pressed
  // before the last one's navigation has re-rendered must start from where that one went.
  const liveItems = useLiveList(items);
  const liveSelection = useLiveSelection(selected?.id ?? null, location.key, location.state);
  const liveSelected = () => {
    const id = liveSelection.current();
    return liveItems.current().find((i) => i.id === id);
  };

  const select = (id: string, extra?: object) => navigate(`/o/${id}${search}`, { replace: true, state: { ...liveSelection.select(id), ...extra } });

  // Where focus goes once a dismissal has re-rendered: a row id, or the heading when the list is empty.
  const pendingFocus = useRef<string | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);

  const dismissSelected = () => {
    const current = liveSelected();
    if (!current) return;
    const list = liveItems.current();
    const index = list.indexOf(current);
    const next = list[index + 1] ?? list[index - 1];
    // If focus is on the row being removed (or already lost), it follows the selection.
    const active = document.activeElement;
    const row = document.getElementById(rowId(current.id));
    if (!active || active === document.body || row?.contains(active)) pendingFocus.current = next ? next.id : HEADING;
    liveItems.markDismissed(current.id);
    // The optional "Why not?" prompt follows; this move to the next item keeps it.
    model.dismiss(current.id, true);
    if (next) select(next.id, DISMISS_NAV);
    else navigate(`/${search}`, { replace: true, state: { ...liveSelection.select(null), ...DISMISS_NAV } });
  };

  useEffect(() => {
    const target = pendingFocus.current;
    if (!target) return;
    if (target !== HEADING && target !== selected?.id) return;
    pendingFocus.current = null;
    if (target === HEADING) headingRef.current?.focus();
    else document.getElementById(rowId(target))?.focus();
  });

  useFeedKeys({
    onNext: () => {
      const list = liveItems.current();
      const current = liveSelected();
      const i = current ? list.indexOf(current) : -1;
      const next = list[Math.min(i + 1, list.length - 1)];
      if (next && next !== current) select(next.id);
    },
    onPrevious: () => {
      const list = liveItems.current();
      const current = liveSelected();
      const i = current ? list.indexOf(current) : 0;
      const prev = list[Math.max(i - 1, 0)];
      if (prev && prev !== current) select(prev.id);
    },
    onSave: () => {
      const current = liveSelected();
      if (current) model.toggleSaved(current.id);
    },
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
      <Sidebar current="/" channel={feed.digest.channel} />

      <main className={styles.main}>
        <div className={styles.head}>
          <div className={styles.greet}>
            <h1 ref={headingRef} tabIndex={-1} className={styles.h1}>
              {greeting(feed.user.name)}
            </h1>
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
            <LiveStatus model={model} />
            <DismissReasonPrompt
              model={model}
              focusAfter={() => {
                const id = liveSelection.current();
                (id ? document.getElementById(rowId(id)) : headingRef.current)?.focus();
              }}
            />
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
  // Only http(s) links to the original notice; anything else renders no link.
  const original = httpUrl(item.detail.originalUrl);
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
        <SaveButton saved={saved} onClick={() => model.toggleSaved(item.id)} />
        <Button variant="secondary" onClick={onDismiss}>
          Not for me
        </Button>
        {original && (
          <TextLink href={original} target="_blank" rel="noopener noreferrer">
            Read the original
          </TextLink>
        )}
      </div>
      {model.live && <LiveDetail key={item.id} model={model} item={item} />}
    </Card>
  );
}
