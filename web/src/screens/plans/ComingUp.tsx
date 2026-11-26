import { m5Api, amountOf, type PlanItem } from '../../api/m5';
import { useResource } from '../../api/useResource';
import { Card } from '../../components/Card/Card';
import { TextButton, TextLink } from '../../components/TextLink/TextLink';
import { methodWords, plannedWhen, shortAmount } from '../../lib/benchmarkWords';
import { httpUrl } from '../../lib/externalUrl';
import { cx } from '../../lib/streams';
import { COPY } from '../common/copy';
import own from '../benchmarks/Benchmarks.module.css';
import styles from '../sources/Sources.module.css';

/** Not on any board (design review). */
export const COMING_UP_COPY = {
  title: 'Coming up',
  help: 'Tenders buyers plan to advertise, from their published procurement plans. They are not open yet, so there is nothing to apply for until the notice appears in your feed.',
  empty: 'No planned tenders match your profiles yet.',
  loading: 'Loading planned tenders…',
  unreachable: `${COPY.unreachableTitle}, so planned tenders are not shown.`,
  estimated: (amount: string) => `Estimated ${amount}`,
  plannedFor: (when: string) => `Planned for ${when}`,
  matches: (profile: string) => `Matches ${profile}`,
  plan: 'Open the plan (opens in a new tab)',
  /** The buyer first, so a list of these links reads apart; the visible words are in the name. */
  planLabel: (entity: string) => `${entity}: open the plan (opens in a new tab)`,
} as const;

/** The plan's facts in one line: method, estimated value when known, and when it is planned for. */
export function planFacts(p: PlanItem): string {
  const value = amountOf(p.estimatedValue);
  const when = plannedWhen(p.plannedFor);
  return [methodWords(p.method), value !== null ? COMING_UP_COPY.estimated(shortAmount(value, p.currency)) : null, when ? COMING_UP_COPY.plannedFor(when) : null]
    .filter(Boolean)
    .join(' · ');
}

/**
 * "Coming up": planned tenders not yet advertised that match the caller's
 * profiles (GET /api/plans). On the Calendar and the Shortlist. Not on any
 * board (design review).
 */
export function ComingUp({ headingId }: { headingId: string }) {
  const res = useResource('plans', (s) => m5Api.plans(s));
  const items = res.data?.items ?? [];
  return (
    <Card gap={10} aria-labelledby={headingId}>
      <h2 id={headingId} className={styles.groupHeading}>
        {COMING_UP_COPY.title}
      </h2>
      <div className={styles.status}>{COMING_UP_COPY.help}</div>
      {!res.data && res.error && res.error.kind !== 'unauthorized' && (
        <div className={styles.actions}>
          <span className={styles.alertStatus}>{COMING_UP_COPY.unreachable}</span>
          <TextButton onClick={res.reload}>{COPY.tryAgain}</TextButton>
        </div>
      )}
      {!res.data && !res.error && <div className={styles.status}>{COMING_UP_COPY.loading}</div>}
      {res.data && items.length === 0 && <div className={styles.status}>{COMING_UP_COPY.empty}</div>}
      {items.length > 0 && (
        <ul className={cx(styles.rows, own.plainList)}>
          {items.map((p) => {
            const url = httpUrl(p.url);
            const facts = planFacts(p);
            return (
              <li key={p.id} className={styles.stackRow}>
                <div className={styles.rowText}>
                  <span className={styles.rowTitle}>{p.entity}</span>
                  <span className={styles.note}>{p.description}</span>
                  {facts && <span className={styles.meta}>{facts}</span>}
                  {p.matchedProfile && <span className={styles.meta}>{COMING_UP_COPY.matches(p.matchedProfile)}</span>}
                </div>
                {url && (
                  <div>
                    <TextLink spacing="stacked" href={url} target="_blank" rel="noopener noreferrer" aria-label={COMING_UP_COPY.planLabel(p.entity)}>
                      {COMING_UP_COPY.plan}
                    </TextLink>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
