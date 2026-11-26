import { useState, type FormEvent } from 'react';
import { useSearchParams } from 'react-router';
import { m5Api, type BenchmarkCategory } from '../../api/m5';
import { useResource } from '../../api/useResource';
import { Button } from '../../components/Button/Button';
import { Card } from '../../components/Card/Card';
import { Field } from '../../components/Field/Field';
import { FilterChip } from '../../components/FilterChip/FilterChip';
import { StateCard } from '../../components/StateCard/StateCard';
import { TextLink } from '../../components/TextLink/TextLink';
import { categorySentence, currencyWord, PERIODS, PERIOD_WORDS, periodFrom, type Period } from '../../lib/benchmarkWords';
import { kigaliToday } from '../../lib/deadline';
import { useAppLink } from '../../lib/useAppLink';
import { LoadState } from '../common/LoadState';
import { AppShell } from '../shell/AppShell';
import { SignIn } from '../SignIn';
import styles from '../sources/Sources.module.css';

/** Not on any board (design review). */
export const BENCHMARKS_COPY = {
  title: 'Benchmarks',
  summary: 'What buyers paid in tenders they have awarded, by kind of work. Use it to see what a contract usually goes for.',
  filtersLabel: 'Show awards from',
  period: 'Period',
  entity: 'Buying organisation',
  entityHint: 'Part of the name is enough, such as RTDA.',
  searchLabel: 'Search by buying organisation',
  search: 'Show',
  clear: 'Clear',
  listLabel: 'Categories',
  listHelp: 'Prices are the winning bids. Each line keeps to one currency.',
  open: 'See the awards',
  /** The category first, so a list of these links reads apart; the visible words are in the name. */
  openLabel: (label: string) => `${label}: see the awards`,
  emptyTitle: 'No awarded contracts yet',
  emptyBody: 'Blackkite shows prices here once it has read awarded contracts.',
  emptyFiltered: (entity: string) => `No awarded contracts from “${entity}” in this period.`,
  emptyPeriod: 'No awarded contracts in this period. Try a longer one.',
  inCurrency: (label: string, currency: string | null) => `${label} (${currencyWord(currency)})`,
} as const;

function parsePeriod(raw: string | null): Period {
  return PERIODS.includes(raw as Period) ? (raw as Period) : '12m';
}

/** A category's heading; the currency is added only when the same category comes in more than one. */
export function categoryHeading(c: BenchmarkCategory, all: BenchmarkCategory[]): string {
  const twice = all.filter((x) => x.category === c.category).length > 1;
  return twice ? BENCHMARKS_COPY.inCurrency(c.label, c.currency) : c.label;
}

/**
 * /benchmarks: awarded-price ranges per category in plain words (spec 8,
 * contract section 6), with a period and a buying-organisation filter kept in
 * the address. Not on any board (design review).
 */
export function Benchmarks() {
  const [search, setSearch] = useSearchParams();
  const link = useAppLink();
  const period = parsePeriod(search.get('period'));
  const entity = (search.get('entity') ?? '').trim();
  const [typed, setTyped] = useState(entity);
  const today = kigaliToday();
  const from = periodFrom(period, today);
  const to = from ? today : undefined;
  const res = useResource(`benchmarks:${from ?? ''}:${entity}`, (s) => m5Api.benchmarks({ from, to, entity }, s));

  const update = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(search);
    for (const [k, v] of Object.entries(changes)) {
      if (v === null || v === '') next.delete(k);
      else next.set(k, v);
    }
    setSearch(next, { replace: true });
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    update({ entity: typed.trim() || null });
  };

  if (res.error?.kind === 'unauthorized') return <SignIn />;
  const list = res.data?.categories ?? [];
  const emptyBody = entity ? BENCHMARKS_COPY.emptyFiltered(entity) : period !== 'all' ? BENCHMARKS_COPY.emptyPeriod : BENCHMARKS_COPY.emptyBody;

  return (
    <AppShell path="/benchmarks" title={BENCHMARKS_COPY.title} summary={BENCHMARKS_COPY.summary}>
      <Card label={BENCHMARKS_COPY.filtersLabel} gap={14} aria-label={BENCHMARKS_COPY.filtersLabel}>
        <div className={styles.group} role="group" aria-labelledby="bm-period">
          <span id="bm-period" className={styles.groupLabel}>
            {BENCHMARKS_COPY.period}
          </span>
          <div className={styles.chips}>
            {PERIODS.map((p) => (
              <FilterChip key={p} stream="all" label={PERIOD_WORDS[p]} selected={period === p} onClick={() => update({ period: p === '12m' ? null : p })} />
            ))}
          </div>
        </div>
        <form className={styles.form} role="search" aria-label={BENCHMARKS_COPY.searchLabel} onSubmit={submit}>
          <Field label={BENCHMARKS_COPY.entity} hint={BENCHMARKS_COPY.entityHint} name="entity" value={typed} maxLength={200} onChange={(e) => setTyped(e.target.value)} />
          <div className={styles.actions}>
            <Button type="submit" variant="secondary">
              {BENCHMARKS_COPY.search}
            </Button>
            {entity && (
              <Button
                variant="secondary"
                onClick={() => {
                  setTyped('');
                  update({ entity: null });
                }}
              >
                {BENCHMARKS_COPY.clear}
              </Button>
            )}
          </div>
        </form>
      </Card>

      <LoadState loading={res.loading} refreshing={res.refreshing} error={res.error} onRetry={res.reload} />
      {res.data && list.length === 0 && (
        <Card gap={12} aria-label="Benchmarks status">
          <StateCard kind="nothing-new" title={BENCHMARKS_COPY.emptyTitle} body={emptyBody} />
        </Card>
      )}
      {list.length > 0 && (
        <Card label={BENCHMARKS_COPY.listLabel} padding="22px 24px 12px" gap={4} aria-label={BENCHMARKS_COPY.listLabel}>
          <div className={styles.status}>{BENCHMARKS_COPY.listHelp}</div>
          <div className={styles.rows}>
            {list.map((c) => {
              const heading = categoryHeading(c, list);
              return (
                <div key={`${c.category}-${c.currency ?? ''}`} className={styles.row}>
                  <div className={styles.rowText}>
                    <span className={styles.rowTitle}>{heading}</span>
                    <span className={styles.meta}>{categorySentence(c)}</span>
                  </div>
                  <div className={styles.side}>
                    <TextLink {...link(`/benchmarks/${encodeURIComponent(c.category)}`)} aria-label={BENCHMARKS_COPY.openLabel(heading)}>
                      {BENCHMARKS_COPY.open}
                    </TextLink>
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      )}
    </AppShell>
  );
}
