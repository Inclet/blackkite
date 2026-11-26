import { useEffect, useState, type FormEvent, type ReactNode } from 'react';
import { useNavigate, useParams } from 'react-router';
import { api, ApiError, refusalOf } from '../../api/client';
import { CURRENCIES, m4Api, type OwnedDetail } from '../../api/m4';
import type { LiveFeedItem } from '../../api/types';
import { primeCache, readCache, useResource } from '../../api/useResource';
import { Button } from '../../components/Button/Button';
import { Card } from '../../components/Card/Card';
import { Field } from '../../components/Field/Field';
import { FilterChip } from '../../components/FilterChip/FilterChip';
import { STREAMS } from '../../lib/streams';
import { COPY } from '../common/copy';
import { LoadState } from '../common/LoadState';
import { AppShell } from '../shell/AppShell';
import { SignIn } from '../SignIn';
import styles from '../sources/Sources.module.css';
import { emptyForm, serverErrors, toForm, toInput, validate, type ItemErrors, type ItemForm } from './itemForm';

/** Not on any board (design review). */
export const ITEM_COPY = {
  add: 'Add an item',
  addTitle: 'Add an item',
  editTitle: 'Edit your item',
  summary: 'Something Blackkite cannot find for you, such as a notice board call or a tip from a contact. Only you can see it.',
  kind: 'What is it?',
  title: 'Title',
  organisation: 'Organisation (optional)',
  deadline: 'Deadline (optional)',
  eventStart: 'Starts (optional)',
  eventEnd: 'Ends (optional)',
  dateHint: 'With the year, such as 7 Dec 2026 or 7 Dec 2026, 5pm.',
  value: 'Value (optional)',
  currency: 'Currency',
  location: 'Location (optional)',
  url: 'Link (optional)',
  urlHint: 'Where you found it, starting with https://.',
  notes: 'Notes (optional)',
  create: 'Add the item',
  save: 'Save changes',
  cancel: 'Cancel',
  checkFields: 'Check the fields marked above.',
  refused: 'Blackkite did not accept some of these details. Check them and try again.',
  unreachable: `${COPY.unreachableTitle}. Nothing was saved; try again.`,
  notOwner: 'Only the person who added an item can edit it.',
  published: 'This item is public now, so it can’t be changed or deleted here. Ask an admin if something is wrong with it.',
  notFound: 'We could not find that item.',
} as const;

/** Dates are typed text, read as the API reads them (lib/itemDates): no native date picker. */
const DATE_FIELD = { hint: ITEM_COPY.dateHint, maxLength: 100, autoComplete: 'off', spellCheck: false };

const CURRENCY_WORDS: Record<string, string> = { RWF: 'FRW', USD: 'USD', EUR: 'EUR' };

/** Keep the cached feed and shortlist in step with a created or edited item, so /o/:id opens it at once. */
export function rememberItem(item: OwnedDetail): void {
  primeCache(`opportunity:${item.id}`, item);
  const feed = readCache<{ items: LiveFeedItem[] }>('feed');
  if (feed) {
    const { detail, ...row } = item;
    const { fields: _f, sources: _s, documents: _d, changes: _c, note: _n, state: _st, dismissReason: _r, ownItem: _o, ...rowDetail } = detail;
    const next = { ...row, detail: rowDetail } as LiveFeedItem;
    const has = feed.items.some((i) => i.id === item.id);
    primeCache('feed', { ...feed, items: has ? feed.items.map((i) => (i.id === item.id ? next : i)) : [...feed.items, next] });
  }
}

/** Drop a deleted item from the cached feed and shortlist. */
export function forgetItem(id: string): void {
  primeCache(`opportunity:${id}`, undefined);
  const feed = readCache<{ items: LiveFeedItem[] }>('feed');
  if (feed) primeCache('feed', { ...feed, items: feed.items.filter((i) => i.id !== id) });
  const shortlist = readCache<LiveFeedItem[]>('shortlist');
  if (shortlist) primeCache('shortlist', shortlist.filter((i) => i.id !== id));
}

/** /items/new and /items/:id/edit: a private manual item (spec 6). */
export function ItemEditor() {
  const { id } = useParams();
  const existing = useResource<OwnedDetail>(id ? `opportunity:${id}` : null, (s) => api.opportunity(id!, s) as Promise<OwnedDetail>);
  if (existing.error?.kind === 'unauthorized') return <SignIn />;
  if (!id) return <Editor />;
  const own = existing.data?.detail.ownItem;
  if (!existing.data || !own || own.published) {
    const why = existing.error?.kind === 'not-found' ? ITEM_COPY.notFound : existing.data ? (own ? ITEM_COPY.published : ITEM_COPY.notOwner) : null;
    return (
      <AppShell path="/items" title={ITEM_COPY.editTitle}>
        <LoadState loading={existing.loading} error={existing.error?.kind === 'not-found' ? null : existing.error} onRetry={existing.reload} />
        {why && (
          <Card aria-label={ITEM_COPY.editTitle}>
            <div className={styles.status}>{why}</div>
          </Card>
        )}
      </AppShell>
    );
  }
  return <Editor id={id} initial={toForm(existing.data)} />;
}

function ChipGroup({ id, label, error, children }: { id: string; label: string; error?: string; children: ReactNode }) {
  return (
    <fieldset className={styles.group} aria-describedby={error ? `${id}-error` : undefined}>
      <legend className={styles.groupLabel}>{label}</legend>
      <div className={styles.chips}>{children}</div>
      {error && (
        <div id={`${id}-error`} className={styles.error}>
          {error}
        </div>
      )}
    </fieldset>
  );
}

function Editor({ id, initial }: { id?: string; initial?: ItemForm }) {
  const navigate = useNavigate();
  const [form, setForm] = useState<ItemForm>(initial ?? emptyForm());
  const [errors, setErrors] = useState<ItemErrors>({});
  const [status, setStatus] = useState<'idle' | 'saving' | 'invalid' | 'refused' | 'published' | 'unreachable'>('idle');
  // The chips offer RWF, USD and EUR, plus whatever three letters the item already has.
  const [currencies] = useState(() => [...new Set<string>([...CURRENCIES, (initial?.currency ?? 'RWF').toUpperCase()])]);
  const title = id ? ITEM_COPY.editTitle : ITEM_COPY.addTitle;

  const set = <K extends keyof ItemForm>(k: K, v: ItemForm[K]) => setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => {
    if (status !== 'invalid') return;
    const el = document.querySelector<HTMLElement>('[aria-invalid="true"], fieldset[aria-describedby] button');
    el?.focus();
  }, [status, errors]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const found = validate(form);
    setErrors(found);
    if (Object.keys(found).length) return setStatus('invalid');
    setStatus('saving');
    try {
      const body = toInput(form);
      const saved = id ? await m4Api.updateItem(id, body) : await m4Api.createItem(body);
      rememberItem(saved);
      navigate(`/o/${encodeURIComponent(saved.id)}`, { replace: Boolean(id) });
    } catch (err) {
      if (err instanceof ApiError && err.kind === 'invalid') {
        const placed = serverErrors(refusalOf(err).errors);
        setErrors(placed);
        setStatus(Object.keys(placed).length ? 'invalid' : 'refused');
      } else if (err instanceof ApiError && err.kind === 'conflict') setStatus('published');
      else setStatus('unreachable');
    }
  };

  const field = (k: Exclude<keyof ItemForm, 'stream' | 'currency'>, label: string, extra: Record<string, unknown> = {}) => (
    <Field label={label} name={k} value={form[k]} error={errors[k]} onChange={(e) => set(k, e.target.value)} {...extra} />
  );

  const message =
    status === 'invalid'
      ? ITEM_COPY.checkFields
      : status === 'refused'
        ? ITEM_COPY.refused
        : status === 'published'
          ? ITEM_COPY.published
          : status === 'unreachable'
            ? ITEM_COPY.unreachable
            : '';

  return (
    <AppShell path="/items" title={title} summary={ITEM_COPY.summary}>
      <form onSubmit={submit} noValidate aria-label={title} className={styles.form}>
        <Card gap={14} aria-label="The item">
          <ChipGroup id="item-stream" label={ITEM_COPY.kind} error={errors.stream}>
            {STREAMS.map((s) => (
              <FilterChip key={s} stream={s} selected={form.stream === s} onClick={() => set('stream', s)} />
            ))}
          </ChipGroup>
          {field('title', ITEM_COPY.title, { required: true, maxLength: 300 })}
          {field('organisation', ITEM_COPY.organisation, { maxLength: 200 })}
          <div className={styles.fields}>
            {form.stream === 'event' ? (
              <>
                {field('eventStart', ITEM_COPY.eventStart, DATE_FIELD)}
                {field('eventEnd', ITEM_COPY.eventEnd, DATE_FIELD)}
              </>
            ) : (
              field('deadline', ITEM_COPY.deadline, DATE_FIELD)
            )}
            {field('location', ITEM_COPY.location, { maxLength: 200 })}
          </div>
          <div className={styles.fields}>
            {field('value', ITEM_COPY.value, { inputMode: 'numeric' })}
            <ChipGroup id="item-currency" label={ITEM_COPY.currency}>
              {currencies.map((c) => (
                <FilterChip key={c} stream="all" label={CURRENCY_WORDS[c] ?? c} selected={form.currency === c} onClick={() => set('currency', c)} />
              ))}
            </ChipGroup>
          </div>
          {field('url', ITEM_COPY.url, { type: 'url', inputMode: 'url', hint: ITEM_COPY.urlHint, maxLength: 2000 })}
          {field('notes', ITEM_COPY.notes, { maxLength: 2000 })}
        </Card>
        <div className={styles.actions}>
          <Button type="submit" disabled={status === 'saving'}>
            {id ? ITEM_COPY.save : ITEM_COPY.create}
          </Button>
          <Button variant="secondary" onClick={() => (id ? navigate(`/o/${encodeURIComponent(id)}`) : navigate(-1))}>
            {ITEM_COPY.cancel}
          </Button>
        </div>
        <div role="status" className={styles.alertStatus}>
          {message}
        </div>
      </form>
    </AppShell>
  );
}
