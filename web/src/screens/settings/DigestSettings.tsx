import { useState, type FormEvent } from 'react';
import { api, ApiError } from '../../api/client';
import type { DigestSettings as Settings } from '../../api/types';
import { useResource } from '../../api/useResource';
import { Button } from '../../components/Button/Button';
import { Card } from '../../components/Card/Card';
import { FilterChip } from '../../components/FilterChip/FilterChip';
import { SwitchRow } from '../../components/SwitchRow/SwitchRow';
import { reference } from '../../fixtures/reference';
import { STREAMS, type Stream } from '../../lib/streams';
import { COPY } from '../common/copy';
import { LoadState } from '../common/LoadState';
import { AppShell } from '../shell/AppShell';
import { SignIn } from '../SignIn';
import styles from './Settings.module.css';

const BOARD_ALERTS = reference.styleguide.fields.alerts;

export const DIGEST_COPY = {
  title: 'Digest',
  summary: 'What Blackkite emails you, and when.',
  weekly: 'Weekly digest',
  weeklyHelp: (address?: string) => (address ? `Every Monday, by email to ${address}.` : 'Every Monday, by email.'),
  /** The Components board's own label and description. */
  alerts: BOARD_ALERTS.label,
  alertsHelp: BOARD_ALERTS.description,
  /** The fit words, never the internal score (CLAUDE.md section 12). */
  threshold: 'Alert me about',
  strongOnly: 'Strong fits only',
  strongAndGood: 'Strong and good fits',
  streams: 'Streams in the digest',
  profileStreams: 'My profiles’ streams',
  save: 'Save digest settings',
  saved: 'Saved.',
  refused: 'Blackkite did not accept these settings. Try again.',
} as const;

/**
 * alertThreshold values (the internal 0-100 score) behind the two choices. The
 * owner may tune them; they sit near the fit-word bands (strong >= 0.7 confidence,
 * good >= 0.6, docs/api-contract.md section 1).
 */
export const ALERT_THRESHOLDS = { strong: 75, good: 60 } as const;

export type AlertChoice = keyof typeof ALERT_THRESHOLDS;

/** Where the choice starts when urgent alerts are switched on (design review). */
export const DEFAULT_ALERT_CHOICE: AlertChoice = 'strong';

/** The choice a stored threshold reads as: at or above the strong value is "strong only". */
export function choiceFor(threshold: number | null): AlertChoice {
  if (threshold === null) return DEFAULT_ALERT_CHOICE;
  return threshold >= ALERT_THRESHOLDS.strong ? 'strong' : 'good';
}

type Status = 'idle' | 'saving' | 'saved' | 'refused' | 'unreachable';

/** /settings/digest (decision 18: weekly on Monday, or off). Not on any board (design review). */
export function DigestSettings() {
  const res = useResource('digest-settings', (s) => api.digestSettings(s));
  // The digest goes to the account's own address; only GET /me says what it is.
  const me = useResource('me', (s) => api.me(s));
  if (res.error?.kind === 'unauthorized') return <SignIn />;
  return (
    <AppShell path="/settings/digest" title={DIGEST_COPY.title} summary={DIGEST_COPY.summary}>
      <LoadState loading={res.loading} error={res.data ? null : res.error} onRetry={res.reload} />
      {res.data && <DigestForm settings={res.data} address={me.data?.email} onSaved={(s) => res.setData(() => s)} />}
    </AppShell>
  );
}

function DigestForm({ settings, address, onSaved }: { settings: Settings; address?: string; onSaved: (s: Settings) => void }) {
  const [weekly, setWeekly] = useState(settings.frequency === 'weekly');
  const [alerts, setAlerts] = useState(settings.alertThreshold !== null);
  const [choice, setChoice] = useState<AlertChoice>(choiceFor(settings.alertThreshold));
  // A stored value the owner set some other way is kept until the choice is changed.
  const [choiceTouched, setChoiceTouched] = useState(false);
  const [streams, setStreams] = useState<Stream[] | null>(settings.streams);
  const [status, setStatus] = useState<Status>('idle');

  const touch = () => status === 'saved' && setStatus('idle');

  const toggleStream = (s: Stream) => {
    touch();
    setStreams((prev) => {
      const cur = prev ?? [];
      const next = cur.includes(s) ? cur.filter((x) => x !== s) : STREAMS.filter((x) => x === s || cur.includes(x));
      return next.length ? next : null;
    });
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const value = !alerts ? null : !choiceTouched && settings.alertThreshold !== null ? settings.alertThreshold : ALERT_THRESHOLDS[choice];
    setStatus('saving');
    // Exactly the keys PUT takes: the API refuses any other.
    const next: Settings = { channel: 'email', frequency: weekly ? 'weekly' : 'off', day: 'mon', alertThreshold: value, streams };
    try {
      const saved = await api.saveDigestSettings(next);
      onSaved(saved && typeof saved === 'object' ? saved : next);
      setStatus('saved');
    } catch (err) {
      setStatus(err instanceof ApiError && err.kind === 'invalid' ? 'refused' : 'unreachable');
    }
  };

  const message =
    status === 'saved'
      ? DIGEST_COPY.saved
      : status === 'refused'
        ? DIGEST_COPY.refused
        : status === 'unreachable'
          ? `${COPY.unreachableTitle}. Your settings were not saved; try again.`
          : '';

  return (
    <form className={styles.form} onSubmit={submit} noValidate aria-label="Digest settings">
      <Card gap={14} aria-label={DIGEST_COPY.weekly}>
        <SwitchRow
          label={DIGEST_COPY.weekly}
          description={DIGEST_COPY.weeklyHelp(address)}
          checked={weekly}
          onChange={(v) => {
            touch();
            setWeekly(v);
          }}
        />
        <fieldset className={styles.group}>
          <legend className={styles.groupLabel}>{DIGEST_COPY.streams}</legend>
          <div className={styles.chips}>
            <FilterChip
              stream="all"
              label={DIGEST_COPY.profileStreams}
              selected={streams === null}
              onClick={() => {
                touch();
                setStreams(null);
              }}
            />
            {STREAMS.map((s) => (
              <FilterChip key={s} stream={s} selected={streams?.includes(s) ?? false} onClick={() => toggleStream(s)} />
            ))}
          </div>
        </fieldset>
      </Card>
      <Card gap={14} aria-label={DIGEST_COPY.alerts}>
        <SwitchRow
          label={DIGEST_COPY.alerts}
          description={DIGEST_COPY.alertsHelp}
          checked={alerts}
          onChange={(v) => {
            touch();
            setAlerts(v);
          }}
        />
        {alerts && (
          // Not on any board: the Filters chips as a one-of-two choice (design review).
          <fieldset className={styles.group}>
            <legend className={styles.groupLabel}>{DIGEST_COPY.threshold}</legend>
            <div className={styles.chips}>
              {(['strong', 'good'] as const).map((c) => (
                <FilterChip
                  key={c}
                  stream="all"
                  label={c === 'strong' ? DIGEST_COPY.strongOnly : DIGEST_COPY.strongAndGood}
                  selected={choice === c}
                  onClick={() => {
                    touch();
                    setChoiceTouched(true);
                    setChoice(c);
                  }}
                />
              ))}
            </div>
          </fieldset>
        )}
      </Card>
      <div className={styles.actions}>
        <Button type="submit" disabled={status === 'saving'}>
          {DIGEST_COPY.save}
        </Button>
      </div>
      <div role="status" className={status === 'saved' ? styles.status : styles.alertStatus}>
        {message}
      </div>
    </form>
  );
}
