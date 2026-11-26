import { useId, useState } from 'react';
import { useParams, useSearchParams } from 'react-router';
import { AWARDS_PAGE, m5Api, type Award, type BenchmarkCategory } from '../../api/m5';
import { useResource } from '../../api/useResource';
import { BackLink } from '../../components/BackLink/BackLink';
import { Button } from '../../components/Button/Button';
import { Card } from '../../components/Card/Card';
import { StateCard } from '../../components/StateCard/StateCard';
import { TextButton, TextLink } from '../../components/TextLink/TextLink';
import { categoryFallbackLabel, categorySentence, fullAmount } from '../../lib/benchmarkWords';
import { formatFullDate } from '../../lib/detailWords';
import { httpUrl } from '../../lib/externalUrl';
import { useAppLink } from '../../lib/useAppLink';
import { LoadState } from '../common/LoadState';
import { AppShell } from '../shell/AppShell';
import { SignIn } from '../SignIn';
import { cx } from '../../lib/streams';
import styles from '../sources/Sources.module.css';
import own from './Benchmarks.module.css';

/** Not on any board (design review). */
export const AWARDS_COPY = {
  back: 'Back to benchmarks',
  listLabel: 'Awarded contracts',
  ref: (ref: string) => `Ref ${ref}`,
  awardedOn: (date: string) => `Awarded ${date}`,
  won: (winner: string, price: string | null) => (price ? `Won by ${winner} at ${price}` : `Won by ${winner}; price not published`),
  wonNoWinner: (price: string) => `Winning price ${price}`,
  noWinner: 'Winner and price not published',
  showBidders: (n: number) => `Show the ${n} ${n === 1 ? 'bidder' : 'bidders'}`,
  hideBidders: (n: number) => `Hide the ${n} ${n === 1 ? 'bidder' : 'bidders'}`,
  biddersLabel: (title: string) => `Bidders: ${title}`,
  noBidders: 'Bidders not published.',
  priceNotPublished: 'price not published',
  winner: 'winner',
  notice: 'Open the notice (opens in a new tab)',
  noticeLabel: (title: string) => `Open the notice (opens in a new tab): ${title}`,
  emptyTitle: 'No awards to show',
  emptyBody: 'Blackkite has no awarded contracts in this category yet.',
  pageOf: (first: number, last: number, total: number) => `Awards ${first}–${last} of ${total}`,
  pageOnly: (first: number, last: number) => `Awards ${first}–${last}`,
  previous: 'Previous awards',
  next: 'More awards',
} as const;

function parsePage(raw: string | null): number {
  const n = Number(raw);
  return Number.isInteger(n) && n > 1 ? n : 1;
}

/**
 * /benchmarks/:category: the awards behind a category, newest first as the API
 * sends them, paged. Each award has its bidder list behind a real disclosure
 * button and a link out to the notice. Not on any board (design review).
 */
export function BenchmarkAwards() {
  const { category = '' } = useParams();
  const [search, setSearch] = useSearchParams();
  const link = useAppLink();
  const page = parsePage(search.get('page'));
  const res = useResource(`awards:${category}:${page}`, (s) => m5Api.awards(category, page, s));
  // The label and the summary sentence come from the category list (all periods).
  const all = useResource('benchmarks::', (s) => m5Api.benchmarks({}, s));

  if (res.error?.kind === 'unauthorized') return <SignIn />;
  const stats: BenchmarkCategory | undefined = all.data?.categories.find((c) => c.category === category);
  const title = res.data?.label ?? stats?.label ?? categoryFallbackLabel(category);
  const currency = res.data?.currency ?? stats?.currency ?? null;
  const awards = res.data?.awards ?? [];
  const total = typeof res.data?.total === 'number' ? res.data.total : null;
  const first = (page - 1) * AWARDS_PAGE + 1;
  const last = first + awards.length - 1;
  const hasNext = total !== null ? last < total : awards.length === AWARDS_PAGE;

  const goto = (p: number) => {
    const next = new URLSearchParams(search);
    if (p <= 1) next.delete('page');
    else next.set('page', String(p));
    setSearch(next);
    requestAnimationFrame(() => document.querySelector<HTMLElement>('h1')?.focus());
  };

  return (
    <AppShell path="/benchmarks" title={title} summary={stats ? categorySentence(stats) : undefined}>
      <div>
        <BackLink {...link('/benchmarks')}>{AWARDS_COPY.back}</BackLink>
      </div>
      <LoadState loading={res.loading} refreshing={res.refreshing} error={res.error} onRetry={res.reload} />
      {res.data && awards.length === 0 && (
        <Card gap={12} aria-label="Awards status">
          <StateCard kind="nothing-new" title={AWARDS_COPY.emptyTitle} body={AWARDS_COPY.emptyBody} />
        </Card>
      )}
      {awards.length > 0 && (
        <Card label={AWARDS_COPY.listLabel} padding="22px 24px 12px" gap={4} aria-label={AWARDS_COPY.listLabel}>
          <div className={styles.status}>{total !== null ? AWARDS_COPY.pageOf(first, last, total) : AWARDS_COPY.pageOnly(first, last)}</div>
          <ul className={cx(styles.rows, own.plainList)}>
            {awards.map((a) => (
              <AwardRow key={a.id} award={a} currency={a.currency ?? currency} />
            ))}
          </ul>
        </Card>
      )}
      {(page > 1 || hasNext) && res.data && (
        <div className={styles.actions}>
          {page > 1 && (
            <Button variant="secondary" onClick={() => goto(page - 1)}>
              {AWARDS_COPY.previous}
            </Button>
          )}
          {hasNext && (
            <Button variant="secondary" onClick={() => goto(page + 1)}>
              {AWARDS_COPY.next}
            </Button>
          )}
        </div>
      )}
    </AppShell>
  );
}

function AwardRow({ award: a, currency }: { award: Award; currency: string | null }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const price = fullAmount(a.winningPrice, currency);
  const won = a.winner ? AWARDS_COPY.won(a.winner, price) : price ? AWARDS_COPY.wonNoWinner(price) : AWARDS_COPY.noWinner;
  const about = [a.entity, a.awardedOn ? AWARDS_COPY.awardedOn(formatFullDate(a.awardedOn)) : null, a.tenderRef ? AWARDS_COPY.ref(a.tenderRef) : null]
    .filter(Boolean)
    .join(' · ');
  const url = httpUrl(a.url);
  const bidders = a.bidders ?? [];
  return (
    <li className={styles.stackRow}>
      <div className={styles.rowText}>
        <span className={styles.rowTitle}>{a.title}</span>
        <span className={styles.meta}>{about}</span>
        <span className={styles.meta}>{won}</span>
      </div>
      {bidders.length === 0 ? (
        <span className={styles.meta}>{AWARDS_COPY.noBidders}</span>
      ) : (
        <div>
          <TextButton spacing="stacked" aria-expanded={open} aria-controls={`${id}-bidders`} onClick={() => setOpen((o) => !o)}>
            {open ? AWARDS_COPY.hideBidders(bidders.length) : AWARDS_COPY.showBidders(bidders.length)}
          </TextButton>
          <ul id={`${id}-bidders`} hidden={!open} className={styles.list} aria-label={AWARDS_COPY.biddersLabel(a.title)}>
            {bidders.map((b, i) => {
              const bid = fullAmount(b.price, currency) ?? AWARDS_COPY.priceNotPublished;
              const isWinner = a.winner !== null && b.name === a.winner;
              return (
                <li key={`${b.name}-${i}`}>
                  {b.name} — {bid}
                  {isWinner ? ` (${AWARDS_COPY.winner})` : ''}
                </li>
              );
            })}
          </ul>
        </div>
      )}
      {url && (
        <div>
          <TextLink spacing="stacked" href={url} target="_blank" rel="noopener noreferrer" aria-label={AWARDS_COPY.noticeLabel(a.title)}>
            {AWARDS_COPY.notice}
          </TextLink>
        </div>
      )}
    </li>
  );
}
