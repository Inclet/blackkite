import { useState, type FormEvent } from 'react';
import { api, ApiError } from '../../api/client';
import type { DigestSettings as Settings } from '../../api/types';
import { useResource } from '../../api/useResource';
import { Button } from '../../components/Button/Button';
import { Card } from '../../components/Card/Card';
import { Field } from '../../components/Field/Field';
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
  threshold: 'Alert threshold, from 0 to 100',
  thresholdError: 'Use a whole number from 0 to 100, such as 70.',
  streams: 'Streams in the digest',
  profileStreams: 'My profiles’ streams',
  save: 'Save digest settings',
  saved: 'Saved.',
  refused: 'Blackkite did not accept these settings. Check the threshold.',
} as const;

/** Where an alert threshold starts when urgent alerts are switched on (design review). */
export const DEFAULT_THRESHOLD = 70;

export function parseThreshold(s: string): number | null {
  const t = s.trim();
  if (!/^\d{1,3}$/.test(t)) return null;
  const n = Number(t);
  return n <= 100 ? n : null;
}

type Status = 'idle' | 'saving' | 'saved' | 'refused' | 'unreachable';

/** /settings/digest (decision 18: weekly on Monday, or off). Not on any board (design review). */
export function DigestSettings() {
  const res = useResource('digest-settings', (s) => api.digestSettings(s));
  if (res.error?.kind === 'unauthorized') return <SignIn />;
  return (
    <AppShell path="/settings/digest" title={DIGEST_COPY.title} summary={DIGEST_COPY.summary}>
      <LoadState loading={res.loading} error={res.data ? null : res.error} onRetry={res.reload} />
      {res.data && <DigestForm settings={res.data} onSaved={(s) => res.setData(() => s)} />}
    </AppShell>
  );
}

function DigestForm({ settings, onSaved }: { settings: Settings; onSaved: (s: Settings) => void }) {
  const [weekly, setWeekly] = useState(settings.frequency === 'weekly');
  const [alerts, setAlerts] = useState(settings.alertThreshold !== null);
  const [threshold, setThreshold] = useState(String(settings.alertThreshold ?? DEFAULT_THRESHOLD));
  const [streams, setStreams] = useState<Stream[] | null>(settings.streams);
  const [error, setError] = useState<string | undefined>();
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
    const value = alerts ? parseThreshold(threshold) : null;
    if (alerts && value === null) {
      setError(DIGEST_COPY.thresholdError);
      return;
    }
    setError(undefined);
    setStatus('saving');
    const next: Settings = { ...settings, channel: 'email', frequency: weekly ? 'weekly' : 'off', day: 'mon', alertThreshold: value, streams };
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
          description={DIGEST_COPY.weeklyHelp(settings.address)}
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
            if (!v) setError(undefined);
          }}
        />
        {alerts && (
          <Field
            className={styles.threshold}
            label={DIGEST_COPY.threshold}
            name="alertThreshold"
            inputMode="numeric"
            value={threshold}
            onChange={(e) => {
              touch();
              setThreshold(e.target.value);
            }}
            error={error}
          />
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
