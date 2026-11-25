import { useState, type FormEvent } from 'react';
import { ApiError, refusalOf } from '../../api/client';
import { sourcesApi, type MemberSource, type Suggestion } from '../../api/sources';
import { useResource } from '../../api/useResource';
import { Button } from '../../components/Button/Button';
import { Card } from '../../components/Card/Card';
import { Field } from '../../components/Field/Field';
import { StateCard } from '../../components/StateCard/StateCard';
import { Switch } from '../../components/Switch/Switch';
import { Tag } from '../../components/Tag/Tag';
import { COPY } from '../common/copy';
import { LoadState } from '../common/LoadState';
import { AppShell } from '../shell/AppShell';
import { SignIn } from '../SignIn';
import styles from './Sources.module.css';
import { formatDay, formatWhen, HEALTH_HELP, HEALTH_WORDS, itemsCount, KIND_WORDS, streamList, SUGGESTION_WORDS } from './words';

export const SOURCES_COPY = {
  title: 'Sources',
  summary: 'Where Blackkite looks for opportunities. Every item links back to the sources that carried it.',
  listLabel: 'Sources Blackkite checks',
  muteHelp: 'Mute a source to stop seeing items only it carries. Items another source also carries stay in your feed.',
  mute: 'Mute',
  muteName: (name: string) => `Mute ${name}`,
  muted: (name: string) => `Muted ${name}. Your feed is being updated.`,
  unmuted: (name: string) => `${name} is back in your feed.`,
  lastWorked: (when: string) => `Last worked ${when}`,
  neverWorked: 'Has not worked yet',
  health: (word: string) => `Health: ${word}`,
  emptyTitle: 'No sources yet',
  emptyBody: 'An admin adds sources. You can suggest one below.',
  suggestLabel: 'Suggest a source',
  suggestHelp: 'An admin looks at every suggestion and decides whether to add it.',
  url: 'Web address',
  covers: 'What it covers',
  why: 'Why it is useful',
  send: 'Send suggestion',
  urlRequired: 'Enter the web address, such as https://www.example.rw.',
  urlInvalid: 'Use the full address, starting with https:// or http://.',
  refused: 'Blackkite did not accept that address. Check it is a public web address.',
  sent: 'Thanks. An admin will look at it; you can follow it below.',
  /** 429 without a detail; the API sends its own sentence ("You can suggest up to 10 sources a day. …"). */
  tooMany: 'You have sent many suggestions today. Please try again tomorrow.',
  yours: 'Your suggestions',
  sentOn: (when: string) => `Sent ${when}`,
} as const;

/** The note the API stores (one field): what the source covers and why it helps. */
export function suggestionNote(covers: string, why: string): string | null {
  const parts = [covers.trim() && `Covers: ${covers.trim()}`, why.trim() && `Why it is useful: ${why.trim()}`].filter(Boolean);
  return parts.length ? parts.join('\n') : null;
}

export function validUrl(v: string): string | null {
  const t = v.trim();
  if (!t) return SOURCES_COPY.urlRequired;
  try {
    const u = new URL(t);
    if ((u.protocol !== 'https:' && u.protocol !== 'http:') || !u.hostname.includes('.')) return SOURCES_COPY.urlInvalid;
  } catch {
    return SOURCES_COPY.urlInvalid;
  }
  return null;
}

/** /sources: the active sources with their health, a mute switch each, and the suggest form. Design review. */
export function Sources() {
  const sources = useResource('sources', (s) => sourcesApi.sources(s));
  const mine = useResource('my-suggestions', (s) => sourcesApi.mySuggestions(s));
  const [notice, setNotice] = useState<{ text: string; alert: boolean } | null>(null);

  if (sources.error?.kind === 'unauthorized' || mine.error?.kind === 'unauthorized') return <SignIn />;

  const toggle = async (src: MemberSource, muted: boolean) => {
    const flip = (value: boolean) => sources.setData((list) => list?.map((s) => (s.id === src.id ? { ...s, muted: value } : s)));
    flip(muted);
    try {
      await (muted ? sourcesApi.mute(src.id) : sourcesApi.unmute(src.id));
      setNotice({ text: muted ? SOURCES_COPY.muted(src.name) : SOURCES_COPY.unmuted(src.name), alert: false });
    } catch {
      flip(!muted);
      setNotice({ text: COPY.actionFailed, alert: true });
    }
  };

  const list = sources.data ?? [];
  return (
    <AppShell path="/sources" title={SOURCES_COPY.title} summary={SOURCES_COPY.summary}>
      <LoadState loading={sources.loading} error={sources.error} onRetry={sources.reload} />
      {sources.data && list.length === 0 && (
        <Card gap={12} aria-label="Sources status">
          <StateCard kind="first-visit" title={SOURCES_COPY.emptyTitle} body={SOURCES_COPY.emptyBody} />
        </Card>
      )}
      {list.length > 0 && (
        <Card label={SOURCES_COPY.listLabel} padding="22px 24px 12px" gap={4} aria-label={SOURCES_COPY.listLabel}>
          <div className={styles.status}>{SOURCES_COPY.muteHelp}</div>
          <div className={styles.rows}>
            {list.map((s) => (
              <SourceRow key={s.id} source={s} onToggle={(v) => void toggle(s, v)} />
            ))}
          </div>
        </Card>
      )}
      <div role="status" className={notice?.alert ? styles.alertStatus : styles.status}>
        {notice?.text ?? ''}
      </div>
      <SuggestForm onSent={(s) => mine.setData((prev) => [s, ...(prev ?? [])])} />
      {mine.data && mine.data.length > 0 && <MySuggestions list={mine.data} />}
    </AppShell>
  );
}

function SourceRow({ source: s, onToggle }: { source: MemberSource; onToggle: (muted: boolean) => void }) {
  const about = [s.publisher, KIND_WORDS[s.kind] ?? s.kind, streamList(s.streams)].filter(Boolean).join(' · ');
  const runs = [s.lastSuccessAt ? SOURCES_COPY.lastWorked(formatWhen(s.lastSuccessAt)) : SOURCES_COPY.neverWorked, itemsCount(s.items30d)].join(' · ');
  return (
    <div className={styles.row}>
      <div className={styles.rowText}>
        <span className={styles.rowTitle}>{s.name}</span>
        <span className={styles.meta}>{about}</span>
        <span className={styles.meta}>{runs}</span>
        <span className={styles.meta}>{HEALTH_HELP[s.health]}</span>
      </div>
      <div className={styles.side}>
        <Tag kind="profile">{SOURCES_COPY.health(HEALTH_WORDS[s.health])}</Tag>
        <span className={styles.switchLabel} aria-hidden="true">
          {SOURCES_COPY.mute}
        </span>
        <Switch checked={s.muted} onChange={onToggle} label={SOURCES_COPY.muteName(s.name)} />
      </div>
    </div>
  );
}

type SendStatus = 'idle' | 'sending' | 'sent' | 'refused' | 'too-many' | 'unreachable';

function SuggestForm({ onSent }: { onSent: (s: Suggestion) => void }) {
  const [url, setUrl] = useState('');
  const [covers, setCovers] = useState('');
  const [why, setWhy] = useState('');
  const [error, setError] = useState<string | undefined>();
  const [status, setStatus] = useState<SendStatus>('idle');
  const [limitText, setLimitText] = useState('');

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const bad = validUrl(url) ?? undefined;
    setError(bad);
    if (bad) {
      setStatus('idle');
      return;
    }
    setStatus('sending');
    try {
      const s = await sourcesApi.suggest(url.trim(), suggestionNote(covers, why));
      onSent(s);
      setUrl('');
      setCovers('');
      setWhy('');
      setStatus('sent');
    } catch (err) {
      if (err instanceof ApiError && err.kind === 'too-many') {
        // Over the daily limit: the API's sentence; what was typed stays, to send tomorrow.
        setLimitText(refusalOf(err).detail ?? SOURCES_COPY.tooMany);
        setStatus('too-many');
      } else setStatus(err instanceof ApiError && err.kind === 'invalid' ? 'refused' : 'unreachable');
    }
  };

  const message =
    status === 'sent'
      ? SOURCES_COPY.sent
      : status === 'refused'
        ? SOURCES_COPY.refused
        : status === 'too-many'
          ? limitText
          : status === 'unreachable'
          ? `${COPY.unreachableTitle}. Your suggestion was not sent; try again.`
          : '';
  return (
    <Card label={SOURCES_COPY.suggestLabel} gap={14}>
      <form onSubmit={submit} noValidate aria-label={SOURCES_COPY.suggestLabel} className={styles.form}>
        <div className={styles.status}>{SOURCES_COPY.suggestHelp}</div>
        <Field label={SOURCES_COPY.url} name="url" type="url" inputMode="url" value={url} error={error} onChange={(e) => setUrl(e.target.value)} />
        <div className={styles.fields}>
          <Field label={SOURCES_COPY.covers} name="covers" value={covers} maxLength={900} onChange={(e) => setCovers(e.target.value)} />
          <Field label={SOURCES_COPY.why} name="why" value={why} maxLength={900} onChange={(e) => setWhy(e.target.value)} />
        </div>
        <div className={styles.actions}>
          <Button type="submit" disabled={status === 'sending'}>
            {SOURCES_COPY.send}
          </Button>
        </div>
        <div role="status" className={status === 'sent' ? styles.status : styles.alertStatus}>
          {message}
        </div>
      </form>
    </Card>
  );
}

function MySuggestions({ list }: { list: Suggestion[] }) {
  return (
    <Card label={SOURCES_COPY.yours} padding="22px 24px 12px" gap={4} aria-label={SOURCES_COPY.yours}>
      <div className={styles.rows}>
        {list.map((s) => (
          <div key={s.id} className={styles.row}>
            <div className={styles.rowText}>
              <span className={styles.rowTitle}>{s.url}</span>
              <span className={styles.meta}>{SOURCES_COPY.sentOn(formatDay(s.createdAt))}</span>
            </div>
            <Tag kind="profile">{SUGGESTION_WORDS[s.status] ?? s.status}</Tag>
          </div>
        ))}
      </div>
    </Card>
  );
}
