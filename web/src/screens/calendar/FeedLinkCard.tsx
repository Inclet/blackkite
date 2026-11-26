import { useRef, useState } from 'react';
import { m4Api } from '../../api/m4';
import { useResource } from '../../api/useResource';
import { Button } from '../../components/Button/Button';
import { Card } from '../../components/Card/Card';
import { Field } from '../../components/Field/Field';
import { COPY } from '../common/copy';
import styles from './Calendar.module.css';

/** Not on any board (design review). */
export const FEED_LINK_COPY = {
  title: 'Add to your calendar app',
  body: 'Your saved items’ deadlines and event dates can appear in the calendar on your phone or computer. In your calendar app, choose to subscribe to a calendar by link, and paste this link. It updates by itself.',
  contains: 'The link shows titles, organisations and dates, with a link back to Blackkite. It never shows your notes, scores or profiles.',
  keep: 'Anyone with the link can see those dates, so keep it to yourself.',
  label: 'Your calendar link',
  copy: 'Copy link',
  copied: 'Link copied.',
  copyFailed: 'Could not copy. Select the link and copy it yourself.',
  stop: 'Stop this link',
  confirm: 'Stop this link? Calendar apps that use it stop updating. You get a new link to add again.',
  confirmYes: 'Stop it and make a new link',
  confirmNo: 'Keep this link',
  stopped: 'The old link no longer works. Add the new one to your calendar app.',
  stopFailed: `${COPY.unreachableTitle}, so the link was not changed. Try again.`,
  loading: 'Getting your link…',
  unreachable: `${COPY.unreachableTitle}, so your link is not shown. Try again later.`,
} as const;

/** The personal calendar feed (GET /api/calendar/feed-link), copy, and "Stop this link" (rotate) with a confirm. */
export function FeedLinkCard() {
  const res = useResource('calendar-feed-link', (s) => m4Api.feedLink(s));
  const [status, setStatus] = useState<{ text: string; alert: boolean } | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const stopRef = useRef<HTMLButtonElement>(null);
  const url = res.data?.url ?? '';

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url);
      setStatus({ text: FEED_LINK_COPY.copied, alert: false });
    } catch {
      inputRef.current?.select();
      setStatus({ text: FEED_LINK_COPY.copyFailed, alert: true });
    }
  };

  const rotate = async () => {
    setBusy(true);
    try {
      const next = await m4Api.rotateFeedLink();
      res.setData(() => next);
      setStatus({ text: FEED_LINK_COPY.stopped, alert: false });
      setConfirming(false);
      // The confirm buttons leave the page; focus goes back to where the user started.
      requestAnimationFrame(() => stopRef.current?.focus());
    } catch {
      setStatus({ text: FEED_LINK_COPY.stopFailed, alert: true });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card gap={14} aria-labelledby="feed-link-title">
      <h2 id="feed-link-title" className={styles.h2}>
        {FEED_LINK_COPY.title}
      </h2>
      <p className={styles.body}>{FEED_LINK_COPY.body}</p>
      <p className={styles.body}>
        {FEED_LINK_COPY.contains} {FEED_LINK_COPY.keep}
      </p>
      {!res.data && <div className={res.error ? styles.alertStatus : styles.status}>{res.error ? FEED_LINK_COPY.unreachable : FEED_LINK_COPY.loading}</div>}
      {res.data && (
        <>
          <Field ref={inputRef} label={FEED_LINK_COPY.label} name="calendar-link" value={url} readOnly onFocus={(e) => e.currentTarget.select()} />
          <div className={styles.actions}>
            <Button onClick={() => void copy()}>{FEED_LINK_COPY.copy}</Button>
            <Button ref={stopRef} variant="secondary" aria-expanded={confirming} onClick={() => setConfirming((c) => !c)}>
              {FEED_LINK_COPY.stop}
            </Button>
          </div>
          {confirming && (
            <div className={styles.confirm} role="group" aria-label={FEED_LINK_COPY.stop}>
              <div className={styles.status}>{FEED_LINK_COPY.confirm}</div>
              <div className={styles.actions}>
                <Button disabled={busy} onClick={() => void rotate()}>
                  {FEED_LINK_COPY.confirmYes}
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => {
                    setConfirming(false);
                    stopRef.current?.focus();
                  }}
                >
                  {FEED_LINK_COPY.confirmNo}
                </Button>
              </div>
            </div>
          )}
        </>
      )}
      <div role="status" className={status?.alert ? styles.alertStatus : styles.status}>
        {status?.text ?? ''}
      </div>
    </Card>
  );
}
