import { useEffect, useRef, useState, type FormEvent, type Ref } from 'react';
import { useLocation } from 'react-router';
import { api } from '../../api/client';
import { DISMISS_REASONS } from '../../api/types';
import { useResource } from '../../api/useResource';
import { Button } from '../../components/Button/Button';
import { Card } from '../../components/Card/Card';
import { DeadlinePill } from '../../components/DeadlinePill/DeadlinePill';
import { Field } from '../../components/Field/Field';
import { StateCard } from '../../components/StateCard/StateCard';
import { FilterChip } from '../../components/FilterChip/FilterChip';
import { FitLine, FitReason } from '../../components/FitLine/FitLine';
import { Flag } from '../../components/Flag/Flag';
import { Icon } from '../../components/Icon/Icon';
import { Tag } from '../../components/Tag/Tag';
import type { FeedItem } from '../../fixtures/types';
import { pillFor } from '../../lib/feed';
import { cx, STREAMS, type Stream } from '../../lib/streams';
import { COPY } from '../common/copy';
import { LoadState } from '../common/LoadState';
import { DISMISS_COPY, isDismissNav, type FeedModel } from './model';
import { OwnItemControls } from './OwnItem';
import { DetailSections } from './DetailSections';
import { useIsDesktop } from '../../lib/useIsDesktop';
import type { OwnedDetail } from '../../api/m4';
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

export const DETAIL_COPY = {
  /** Next to the profile tag when the matched profile is provisional (spec 7.1). Not on any board (design review). */
  provisional: 'Provisional',
} as const;

/**
 * Whether the profile (and Provisional) tags belong on the item. Tenders and
 * funding are scored: with no fit word (null or "not-scored") no match was made,
 * so a profile tag would imply one. Events and investments are never given a fit
 * word (contract: fit null by design) and keep the profile the API sends.
 */
export function showsProfile(item: FeedItem): boolean {
  if (!item.detail.profile) return false;
  if (item.fit === 'not-scored') return false;
  return item.fit !== null || (item.stream !== 'tender' && item.stream !== 'funding');
}

/** Stream tag, profile tag (and "Provisional" when the profile is) and the deadline pill. */
export function DetailTop({ item, tagGap }: { item: FeedItem; tagGap: 6 | 8 }) {
  const profile = showsProfile(item);
  return (
    <div className={cx(styles.top, tagGap === 6 ? styles.topPhone : undefined)}>
      <span className={styles.tags}>
        <Tag kind="stream" stream={item.stream} />
        {profile && <Tag kind="profile">{item.detail.profile}</Tag>}
        {profile && item.provisional && <Tag kind="profile">{DETAIL_COPY.provisional}</Tag>}
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

export const SAVE_LABEL = 'Save to shortlist';

/**
 * "Save to shortlist". Unpressed: the primary button, as on the boards. Pressed
 * (saved): the secondary button with the check icon before the same label. The
 * boards never show a saved item, so the pressed look is not on any board (design review).
 */
export function SaveButton({ saved, size, onClick }: { saved: boolean; size?: 'regular' | 'large'; onClick: () => void }) {
  return (
    <Button
      size={size}
      variant={saved ? 'secondary' : 'primary'}
      aria-pressed={saved}
      onClick={onClick}
      className={saved ? styles.saved : undefined}
    >
      {saved && <Icon name="check" size={16} strokeWidth={1.6} />}
      {SAVE_LABEL}
    </Button>
  );
}

/** Marks the reason chips' group, so the screens can tell when focus is inside the prompt. */
export const DISMISS_PROMPT_ATTR = 'data-dismiss-prompt';

/** True when focus is on one of the prompt's chips. */
export function focusInDismissPrompt(): boolean {
  return document.activeElement?.closest(`[${DISMISS_PROMPT_ATTR}]`) != null;
}

/**
 * "Why not? (optional)" after "Not for me" / X: the five reasons as one-shot
 * FilterChips (`action`: no aria-pressed). The item is already dismissed; a chip
 * sends the reason. Gone after a choice or on the next navigation (the
 * dismissal's own move to the next item does not count): J/K close it by design,
 * since moving on means the user chose not to answer.
 *
 * Focus: after X it stays where it was, so J/K/S/X carry on and Tab reaches the
 * chips. After the desktop pane's "Not for me" button the screen moves focus to
 * the first chip (`firstChipRef`). Design review.
 */
export function DismissReasonPrompt({
  model,
  className,
  padding,
  focusAfter,
  firstChipRef,
}: {
  model: FeedModel;
  className?: string;
  padding?: string;
  /** Where focus goes when a chip is chosen (the prompt and the chip leave the page). */
  focusAfter: () => void;
  firstChipRef?: Ref<HTMLButtonElement>;
}) {
  const prompt = model.dismissPrompt;
  if (!prompt) return null;
  const labelId = `why-not-${prompt.id}`;
  return (
    <Card className={className} padding={padding ?? '16px'} gap={10} aria-label={`${DISMISS_COPY.question}: ${prompt.title}`}>
      <div className={styles.whyLabel} id={labelId}>
        {DISMISS_COPY.question}
      </div>
      <div className={styles.progress} role="group" aria-labelledby={labelId} {...{ [DISMISS_PROMPT_ATTR]: '' }}>
        {DISMISS_REASONS.map((r, i) => (
          <FilterChip
            key={r}
            ref={i === 0 ? firstChipRef : undefined}
            stream="all"
            action
            label={DISMISS_COPY.reasons[r]}
            onClick={() => {
              model.chooseDismissReason(r);
              focusAfter();
            }}
          />
        ))}
      </div>
    </Card>
  );
}

/**
 * Closes the "Why not?" prompt on the next navigation, except the dismissal's own
 * move (tagged DISMISS_NAV). Called where the feed state lives (FeedRoute), so it
 * sees every move between the feed and an item, whichever screen is showing.
 */
export function useDismissPromptLifetime(model: FeedModel): void {
  const { key, state } = useLocation();
  const lastKey = useRef(key);
  const { closeDismissPrompt } = model;
  useEffect(() => {
    if (lastKey.current === key) return;
    lastKey.current = key;
    if (!isDismissNav(state)) closeDismissPrompt();
  }, [key, state, closeDismissPrompt]);
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
  const desktop = useIsDesktop();
  const detail = useResource<OwnedDetail>(`opportunity:${item.id}`, (s) => api.opportunity(item.id, s) as Promise<OwnedDetail>);
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
      {detail.data?.detail.ownItem && <OwnItemControls item={item} detail={detail} model={model} />}
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
      {detail.data && <DetailSections detail={detail.data.detail} collapsible={!desktop} headingLevel={desktop ? 3 : 2} />}
    </div>
  );
}
