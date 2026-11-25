import { useEffect, useRef, useState, type FormEvent } from 'react';
import { api } from '../../api/client';
import { useResource } from '../../api/useResource';
import { Button } from '../../components/Button/Button';
import { Card } from '../../components/Card/Card';
import { DeadlinePill } from '../../components/DeadlinePill/DeadlinePill';
import { Field } from '../../components/Field/Field';
import { StateCard } from '../../components/StateCard/StateCard';
import { FilterChip } from '../../components/FilterChip/FilterChip';
import { FitLine, FitReason } from '../../components/FitLine/FitLine';
import { Flag } from '../../components/Flag/Flag';
import { Tag } from '../../components/Tag/Tag';
import type { FeedItem } from '../../fixtures/types';
import { pillFor } from '../../lib/feed';
import { cx, STREAMS, type Stream } from '../../lib/streams';
import { COPY } from '../common/copy';
import { LoadState } from '../common/LoadState';
import type { FeedModel } from './model';
import styles from './parts.module.css';

/** All, then the four streams (the desktop board shows all four; the phone's Events chip scrolls off-screen, decision 4). */
export function FilterChips({ model, className, chipClassName }: { model: FeedModel; className?: string; chipClassName?: string }) {
  const options: (Stream | 'all')[] = ['all', ...STREAMS];
  return (
    <div className={className} role="group" aria-label="Filter by stream">
      {options.map((s) => (
        <FilterChip key={s} stream={s} selected={model.filter === s} onClick={() => model.setFilter(s)} className={chipClassName} />
      ))}
    </div>
  );
}

/** Stream tag, profile tag and the deadline pill. */
export function DetailTop({ item, tagGap }: { item: FeedItem; tagGap: 6 | 8 }) {
  return (
    <div className={cx(styles.top, tagGap === 6 ? styles.topPhone : undefined)}>
      <span className={styles.tags}>
        <Tag kind="stream" stream={item.stream} />
        {item.detail.profile && <Tag kind="profile">{item.detail.profile}</Tag>}
      </span>
      <DeadlinePill {...pillFor(item)} />
    </div>
  );
}

/** "Strong fit · why this matched", the reasons and the "To check" note. Nothing for unscored items. */
export function FitSection({ item }: { item: FeedItem }) {
  if (!item.fit || item.fit === 'not-scored') return null;
  return (
    <>
      <FitLine level={item.fit} variant="heading" reason="why this matched" />
      {item.detail.reasons.map((r) => (
        <FitReason key={r}>{r}</FitReason>
      ))}
      {item.detail.toCheck && <Flag variant="note">{item.detail.toCheck}</Flag>}
    </>
  );
}

export function hasFitSection(item: FeedItem): boolean {
  return item.fit !== null && item.fit !== 'not-scored';
}

/** Announces save and dismiss to screen readers. */
export function LiveRegion({ message }: { message: string }) {
  return (
    <div role="status" aria-live="polite" className={styles.visuallyHidden}>
      {message}
    </div>
  );
}

export const LIVE_COPY = {
  progress: 'Your progress',
  acting: 'Acting on it',
  done: 'Done',
  note: 'Your note',
  saveNote: 'Save note',
  noteSaved: 'Note saved.',
  noteFailed: 'We could not reach Blackkite just now. Your note was not saved; try again.',
} as const;

/**
 * Live data only: the loading or unreachable card, and the notice that a change
 * was undone because it did not reach the server. Nothing on fixtures.
 */
export function LiveStatus({ model, className, padding }: { model: FeedModel; className?: string; padding?: string }) {
  if (!model.live) return null;
  return (
    <>
      <LoadState {...model.live.status} className={className} padding={padding} />
      {model.live.failed && (
        <Card className={className} padding={padding} gap={12} aria-label="Change not saved">
          <StateCard kind="source-down" title={COPY.unreachableTitle} body={COPY.actionFailed} />
        </Card>
      )}
    </>
  );
}

/**
 * Live data only, under the detail actions: "Acting on it" and "Done" (spec 8,
 * mark acting/done) and the user's note, each saved with PUT. Not on any board:
 * FilterChip and Field from the Components board (design review).
 */
export function LiveDetail({ model, item }: { model: FeedModel; item: FeedItem }) {
  const live = model.live!;
  const detail = useResource(`opportunity:${item.id}`, (s) => api.opportunity(item.id, s));
  const state = live.stateOf(item.id);
  const [note, setNote] = useState('');
  const [noteStatus, setNoteStatus] = useState<'idle' | 'saving' | 'saved' | 'failed'>('idle');
  const typed = useRef(false);
  const loadedNote = detail.data?.detail.note ?? '';

  useEffect(() => {
    if (!typed.current) setNote(loadedNote);
  }, [loadedNote]);

  const toggle = (s: 'acting' | 'done') => live.setState(item.id, state === s ? 'saved' : s);

  const saveNote = async (e: FormEvent) => {
    e.preventDefault();
    setNoteStatus('saving');
    try {
      await api.setNote(item.id, note);
      detail.setData((prev) => prev && { ...prev, detail: { ...prev.detail, note } });
      setNoteStatus('saved');
    } catch {
      setNoteStatus('failed');
    }
  };

  return (
    <div className={styles.live}>
      <div className={styles.liveLabel} id={`progress-${item.id}`}>
        {LIVE_COPY.progress}
      </div>
      <div className={styles.progress} role="group" aria-labelledby={`progress-${item.id}`}>
        <FilterChip stream="all" label={LIVE_COPY.acting} selected={state === 'acting'} onClick={() => toggle('acting')} />
        <FilterChip stream="all" label={LIVE_COPY.done} selected={state === 'done'} onClick={() => toggle('done')} />
      </div>
      <form className={styles.note} onSubmit={saveNote}>
        <Field
          label={LIVE_COPY.note}
          name="note"
          value={note}
          maxLength={2000}
          onChange={(e) => {
            typed.current = true;
            setNote(e.target.value);
            if (noteStatus !== 'saving') setNoteStatus('idle');
          }}
          error={noteStatus === 'failed' ? LIVE_COPY.noteFailed : undefined}
        />
        <div className={styles.noteRow}>
          <Button type="submit" variant="secondary" disabled={noteStatus === 'saving'}>
            {LIVE_COPY.saveNote}
          </Button>
          <span role="status" className={styles.noteStatus}>
            {noteStatus === 'saved' ? LIVE_COPY.noteSaved : ''}
          </span>
        </div>
      </form>
    </div>
  );
}
