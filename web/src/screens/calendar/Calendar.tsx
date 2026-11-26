import { useRef, type KeyboardEvent, type MouseEvent } from 'react';
import { useNavigate, useSearchParams } from 'react-router';
import { m4Api, type CalendarDay, type CalendarEntry, type CalendarKind } from '../../api/m4';
import { useResource } from '../../api/useResource';
import { Button } from '../../components/Button/Button';
import { Card } from '../../components/Card/Card';
import { DeadlinePill } from '../../components/DeadlinePill/DeadlinePill';
import { FilterChip } from '../../components/FilterChip/FilterChip';
import { FitLine } from '../../components/FitLine/FitLine';
import { Icon } from '../../components/Icon/Icon';
import { Tag } from '../../components/Tag/Tag';
import { addDays, currentMonth, dayTitle, formatTime, monthRange, monthTitle, monthWeeks, parseMonth, shiftMonth, WEEKDAYS, type Month } from '../../lib/calendar';
import { daysLeft, kigaliToday } from '../../lib/deadline';
import { STREAM_COLOURS, STREAM_NAMES, cx } from '../../lib/streams';
import { isModifiedClick } from '../../lib/useAppLink';
import { useIsDesktop } from '../../lib/useIsDesktop';
import { LoadState } from '../common/LoadState';
import { AppShell } from '../shell/AppShell';
import { SignIn } from '../SignIn';
import { ComingUp } from '../plans/ComingUp';
import { FeedLinkCard } from './FeedLinkCard';
import styles from './Calendar.module.css';

/** Wording on the calendar. Not on any board (design review). */
export const CALENDAR_COPY = {
  title: 'Calendar',
  summary: 'Deadlines and event dates from your feed, by day.',
  show: 'Show',
  kinds: { all: 'All', deadlines: 'Deadlines', events: 'Events' } satisfies Record<CalendarKind, string>,
  savedOnly: 'Saved only',
  view: 'View',
  month: 'Month',
  list: 'List',
  previous: 'Previous month',
  next: 'Next month',
  thisMonth: 'This month',
  today: 'Today',
  empty: (month: string) => `Nothing in ${month} with these settings.`,
  gridHint: 'Arrow keys move between days. The list view shows the same dates as a list.',
} as const;

const KINDS: readonly CalendarKind[] = ['all', 'deadlines', 'events'];

/** "Closes 5pm", "Starts", "Ended": past dates in the past tense. */
export function entryLabel(entry: CalendarEntry, date: string): string {
  const past = daysLeft(date) < 0;
  const word =
    entry.kind === 'deadline' ? (past ? 'Closed' : 'Closes') : entry.kind === 'event_start' ? (past ? 'Started' : 'Starts') : entry.kind === 'event_end' ? (past ? 'Ended' : 'Ends') : 'Event';
  return entry.time ? `${word} ${formatTime(entry.time)}` : word;
}

/** The pill: deadlines escalate as DeadlinePill does; event days count from that day (decision 23). */
function EntryPill({ entry, date, className }: { entry: CalendarEntry; date: string; className?: string }) {
  const label = entryLabel(entry, date);
  if (entry.kind === 'deadline') return <DeadlinePill deadline={date} label={label} size="small" className={className} />;
  return <DeadlinePill event={{ start: date, end: date }} label={label} size="small" className={className} />;
}

function EntryFit({ entry }: { entry: CalendarEntry }) {
  if (!entry.fit || entry.fit === 'not-scored') return null;
  return <FitLine level={entry.fit} />;
}

function Tile({ entry, small }: { entry: CalendarEntry; small?: boolean }) {
  return (
    <span className={small ? styles.tileSmall : styles.tile} style={{ background: STREAM_COLOURS[entry.stream].tint }}>
      <Icon name={entry.stream} label={STREAM_NAMES[entry.stream]} size={small ? 14 : 18} strokeWidth={1.4} stroke={STREAM_COLOURS[entry.stream].text} />
    </span>
  );
}

/** An entry is a link to the item; plain clicks stay in the app. */
function useEntryLink() {
  const navigate = useNavigate();
  return (id: string) => {
    const href = `/o/${encodeURIComponent(id)}`;
    return {
      href,
      onClick: (e: MouseEvent<HTMLAnchorElement>) => {
        if (e.defaultPrevented || isModifiedClick(e)) return;
        e.preventDefault();
        navigate(href);
      },
    };
  };
}

export function Calendar() {
  const desktop = useIsDesktop();
  const [search, setSearch] = useSearchParams();
  const month = parseMonth(search.get('month'));
  const kindParam = search.get('show');
  const kind: CalendarKind = KINDS.includes(kindParam as CalendarKind) ? (kindParam as CalendarKind) : 'all';
  const saved = search.get('saved') === '1';
  const view = desktop && search.get('view') !== 'list' ? 'month' : 'list';
  const { from, to } = monthRange(month);
  const res = useResource(`calendar:${from}:${to}:${kind}:${saved}`, (s) => m4Api.calendar({ from, to, kind, saved }, s));

  const update = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(search);
    for (const [k, v] of Object.entries(changes)) {
      if (v === null) next.delete(k);
      else next.set(k, v);
    }
    setSearch(next, { replace: true });
  };

  if (res.error?.kind === 'unauthorized') return <SignIn />;
  const days = res.data?.days.filter((d) => d.entries.length > 0) ?? [];
  const title = monthTitle(month);

  return (
    <AppShell path="/calendar" title={CALENDAR_COPY.title} summary={CALENDAR_COPY.summary} wide={view === 'month'}>
      <Card gap={14} aria-label="Calendar settings">
        <div className={styles.controls}>
          <div className={styles.group} role="group" aria-labelledby="cal-show">
            <span id="cal-show" className={styles.groupLabel}>
              {CALENDAR_COPY.show}
            </span>
            <div className={styles.chips}>
              {KINDS.map((k) => (
                <FilterChip key={k} stream="all" label={CALENDAR_COPY.kinds[k]} selected={kind === k} onClick={() => update({ show: k === 'all' ? null : k })} />
              ))}
              <FilterChip stream="all" label={CALENDAR_COPY.savedOnly} selected={saved} onClick={() => update({ saved: saved ? null : '1' })} />
            </div>
          </div>
          {desktop && (
            <div className={styles.group} role="group" aria-labelledby="cal-view">
              <span id="cal-view" className={styles.groupLabel}>
                {CALENDAR_COPY.view}
              </span>
              <div className={styles.chips}>
                <FilterChip stream="all" label={CALENDAR_COPY.month} selected={view === 'month'} onClick={() => update({ view: null })} />
                <FilterChip stream="all" label={CALENDAR_COPY.list} selected={view === 'list'} onClick={() => update({ view: 'list' })} />
              </div>
            </div>
          )}
        </div>
      </Card>

      <Card gap={14} aria-labelledby="cal-month">
        <div className={styles.monthBar}>
          <h2 id="cal-month" className={styles.h2} aria-live="polite">
            {title}
          </h2>
          <div className={styles.monthButtons}>
            {month !== currentMonth() && (
              <Button variant="secondary" onClick={() => update({ month: null })}>
                {CALENDAR_COPY.thisMonth}
              </Button>
            )}
            <Button variant="secondary" onClick={() => update({ month: shiftMonth(month, -1) })}>
              {CALENDAR_COPY.previous}
            </Button>
            <Button variant="secondary" onClick={() => update({ month: shiftMonth(month, 1) })}>
              {CALENDAR_COPY.next}
            </Button>
          </div>
        </div>
        <LoadState loading={res.loading} refreshing={res.refreshing} error={res.error} onRetry={res.reload} />
        {res.data && days.length === 0 && <div className={styles.status}>{CALENDAR_COPY.empty(title)}</div>}
        {res.data && view === 'month' && <MonthGrid month={month} days={days} />}
        {res.data && view === 'list' && days.length > 0 && <DayList days={days} />}
      </Card>

      <ComingUp headingId="cal-coming-up" />

      <FeedLinkCard />
    </AppShell>
  );
}

/** The list by day: on the phone, and the accessible alternative to the grid on desktop. */
function DayList({ days }: { days: CalendarDay[] }) {
  const link = useEntryLink();
  const today = kigaliToday();
  return (
    <ol className={styles.days} aria-label="Days">
      {days.map((d) => (
        <li key={d.date} className={styles.day} aria-current={d.date === today ? 'date' : undefined}>
          <h3 className={styles.dayTitle}>
            {dayTitle(d.date)}
            {d.date === today && <Tag kind="profile">{CALENDAR_COPY.today}</Tag>}
          </h3>
          <ul className={styles.entries}>
            {d.entries.map((e) => (
              <li key={`${e.id}-${e.kind}`}>
                <a {...link(e.id)} className={styles.entry}>
                  <Tile entry={e} />
                  <span className={styles.entryBody}>
                    <span className={styles.entryTitle}>{e.title}</span>
                    <span className={styles.entryMeta}>
                      <EntryPill entry={e} date={d.date} />
                      <EntryFit entry={e} />
                      {e.organisationShort && <span className={styles.org}>{e.organisationShort}</span>}
                    </span>
                  </span>
                </a>
              </li>
            ))}
          </ul>
        </li>
      ))}
    </ol>
  );
}

/**
 * The month as a table of days (Monday first). Entries are links in Tab order;
 * arrow keys move between days that have entries (left/right a day, up/down a week).
 */
function MonthGrid({ month, days }: { month: Month; days: CalendarDay[] }) {
  const link = useEntryLink();
  const today = kigaliToday();
  const byDate = new Map(days.map((d) => [d.date, d.entries]));
  const tableRef = useRef<HTMLTableElement>(null);
  const { from, to } = monthRange(month);

  const onKeyDown = (e: KeyboardEvent<HTMLTableElement>) => {
    const step = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }[e.key];
    const current = (e.target as HTMLElement).closest<HTMLElement>('[data-date]')?.dataset.date;
    if (!step || !current || e.altKey || e.ctrlKey || e.metaKey) return;
    // The nearest day with entries in that direction, starting one step away.
    for (let d = addDays(current, step); d >= from && d <= to; d = addDays(d, step > 0 ? 1 : -1)) {
      if (byDate.has(d)) {
        e.preventDefault();
        tableRef.current?.querySelector<HTMLElement>(`[data-date="${d}"] a`)?.focus();
        return;
      }
    }
  };

  return (
    <>
      <p className={styles.hint}>{CALENDAR_COPY.gridHint}</p>
      <div className={styles.gridWrap}>
      <table ref={tableRef} className={styles.grid} aria-label={monthTitle(month)} onKeyDown={onKeyDown}>
        <thead>
          <tr>
            {WEEKDAYS.map((w) => (
              <th key={w.short} scope="col" className={styles.weekday}>
                <abbr title={w.long}>{w.short}</abbr>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {monthWeeks(month).map((week, i) => (
            <tr key={i}>
              {week.map((date, j) => {
                if (!date) return <td key={j} className={styles.outside} />;
                const entries = byDate.get(date) ?? [];
                const isToday = date === today;
                return (
                  <td key={date} data-date={date} className={styles.cell} aria-current={isToday ? 'date' : undefined}>
                    <span className={cx(styles.dayNum, isToday && styles.todayNum)} aria-hidden="true">
                      {Number(date.slice(8))}
                    </span>
                    <span className={styles.visuallyHidden}>{isToday ? `${CALENDAR_COPY.today}, ${dayTitle(date)}` : dayTitle(date)}</span>
                    {entries.map((e) => (
                      <a key={`${e.id}-${e.kind}`} {...link(e.id)} className={styles.cellEntry}>
                        <span className={styles.cellTop}>
                          <Tile entry={e} small />
                          <span className={styles.cellTitle}>{e.title}</span>
                        </span>
                        <span className={styles.cellMeta}>
                          <EntryPill entry={e} date={date} className={styles.cellPill} />
                          <EntryFit entry={e} />
                        </span>
                      </a>
                    ))}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </>
  );
}
