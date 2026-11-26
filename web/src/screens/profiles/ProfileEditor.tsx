import { useEffect, useId, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { useNavigate, useParams } from 'react-router';
import { api, ApiError } from '../../api/client';
import type { Profile, ProfileType } from '../../api/types';
import { primeCache, useResource } from '../../api/useResource';
import { Button } from '../../components/Button/Button';
import { Card } from '../../components/Card/Card';
import { Field } from '../../components/Field/Field';
import { FilterChip } from '../../components/FilterChip/FilterChip';
import { SwitchRow } from '../../components/SwitchRow/SwitchRow';
import { STREAMS, type Stream } from '../../lib/streams';
import { COPY } from '../common/copy';
import { LoadState } from '../common/LoadState';
import { AppShell } from '../shell/AppShell';
import { SignIn } from '../SignIn';
import {
  chipOptions,
  EVENT_TOPICS,
  INSTRUMENTS,
  ORGANISATION_TYPES,
  toForm,
  toInput,
  validate,
  type FormErrors,
  type NumberField,
  type ProfileForm,
} from './profileForm';
import styles from './Profiles.module.css';

export const EDITOR_COPY = {
  newBusiness: 'New business profile',
  newPersonal: 'New personal profile',
  summary: 'Leave anything you do not know empty. Blackkite flags what to check instead of hiding items.',
  about: 'About',
  name: 'Profile name',
  location: 'Based in',
  locations: 'Other places you work, separated by commas',
  locationsHint: 'Such as Musanze, Rubavu. Leave empty if you work only where you are based.',
  organisationType: 'Type of organisation',
  organisationTypeHint: 'Some calls are only for NGOs. Without an answer, this profile counts as not an NGO.',
  active: 'Use this profile',
  activeHelp: 'When off, nothing is ranked against it.',
  streams: 'Streams',
  offer: 'What you offer',
  services: 'Services, separated by commas',
  sectors: 'Sectors you work in, separated by commas',
  sectorsHint: 'Such as logistics, agriculture. Used to find calls for your sector.',
  provisional: 'Provisional',
  provisionalHelp: 'Matches are labelled provisional until you confirm these services.',
  registrations: 'Registrations',
  held: 'Registrations and certificates held',
  notHeld: 'Not held yet',
  capacity: 'Capacity',
  capacityModel: 'How your capacity works',
  trucks: 'Trucks in your network',
  refrigerated: 'Refrigerated trucks',
  owned: 'Trucks you own',
  tonnageMin: 'Smallest load (tonnes)',
  tonnageMax: 'Largest load (tonnes)',
  minContract: 'Smallest contract worth bidding (FRW)',
  interests: 'Interests',
  instruments: 'Instruments',
  ticketMin: 'Smallest ticket (FRW)',
  ticketMax: 'Largest ticket (FRW)',
  topics: 'Event topics',
  horizon: 'How long you can invest for',
  horizonHint: 'Such as 1 to 3 years, or 10 years and more.',
  availability: 'When you can go to events',
  availabilityHint: 'Such as weekday evenings, or weekends.',
  budget: 'Most you would spend on one event (FRW)',
  exclusions: 'Leave out',
  excludeOrganisations: 'Organisations',
  excludeSectors: 'Sectors',
  excludeKeywords: 'Keywords',
  save: 'Save profile',
  create: 'Add profile',
  cancel: 'Back to profiles',
  saved: 'Saved. Open items are being ranked against it again.',
  created: 'Profile added. Open items are being ranked against it.',
  deleted: 'Profile deleted.',
  checkFields: 'Some answers need a fix. They are marked above.',
  refused: 'Blackkite did not accept this profile. Check the name is not used by another of your profiles.',
  delete: 'Delete this profile',
  confirmDelete: (name: string) => `Delete ${name}? Its rankings go with it. This cannot be undone.`,
  confirm: 'Delete',
  keep: 'Keep it',
  notFound: 'We could not find that profile.',
} as const;

/** The form keys held as text. */
type TextKey = { [K in keyof ProfileForm]: ProfileForm[K] extends string ? K : never }[keyof ProfileForm];

type Status = 'idle' | 'saving' | 'saved' | 'invalid' | 'refused' | 'unreachable';

/** /profiles/new/:type and /profiles/:id. Not on any board: Field, Switch, FilterChip and Button (design review). */
export function ProfileEditor() {
  const { id, type } = useParams();
  const profiles = useResource('profiles', (s) => api.profiles(s));
  if (profiles.error?.kind === 'unauthorized') return <SignIn />;

  if (!id) {
    const t: ProfileType = type === 'personal' ? 'personal' : 'business';
    return <Editor key={`new-${t}`} profile={null} type={t} onSaved={() => profiles.reload()} />;
  }
  const profile = profiles.data?.find((p) => p.id === id);
  if (!profile) {
    return (
      <AppShell path="/profiles" title="Profile">
        <LoadState loading={profiles.loading} error={profiles.error} onRetry={profiles.reload} />
        {profiles.data && (
          <Card aria-label="Not found">
            <div className={styles.status}>{EDITOR_COPY.notFound}</div>
          </Card>
        )}
      </AppShell>
    );
  }
  return <Editor key={profile.id} profile={profile} type={profile.type} onSaved={() => profiles.reload()} />;
}

/** The offered organisation types, then a stored word the list does not have (kept as written). */
function organisationOptions(current: string): { value: string; label: string }[] {
  const base: { value: string; label: string }[] = ORGANISATION_TYPES.map((o) => ({ ...o }));
  return current && !base.some((o) => o.value === current) ? [...base, { value: current, label: current }] : base;
}

function ChipGroup({ label, hint, error, children }: { label: string; hint?: string; error?: string; children: ReactNode }) {
  const errorId = useId();
  const hintId = useId();
  const described = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(' ') || undefined;
  return (
    <fieldset className={styles.group} aria-describedby={described}>
      <legend className={styles.groupLabel}>{label}</legend>
      {hint && (
        <div id={hintId} className={styles.hint}>
          {hint}
        </div>
      )}
      <div className={styles.chips}>{children}</div>
      {error && (
        <div id={errorId} className={styles.error}>
          {error}
        </div>
      )}
    </fieldset>
  );
}

function Editor({ profile, type, onSaved }: { profile: Profile | null; type: ProfileType; onSaved: () => void }) {
  const navigate = useNavigate();
  const [form, setForm] = useState<ProfileForm>(() => toForm(profile, type));
  const [errors, setErrors] = useState<FormErrors>({});
  const [status, setStatus] = useState<Status>('idle');
  const [confirming, setConfirming] = useState(false);
  const [deleteFailed, setDeleteFailed] = useState(false);

  // A fresh copy from the server (after save) resets the form; the copy it started from does not.
  const shown = useRef(profile);
  useEffect(() => {
    if (!profile || profile === shown.current) return;
    shown.current = profile;
    setForm(toForm(profile, profile.type));
  }, [profile]);

  const set = <K extends keyof ProfileForm>(key: K, value: ProfileForm[K]) => {
    setForm((f) => ({ ...f, [key]: value }));
    if (status === 'saved') setStatus('idle');
  };
  const toggle = (key: 'instruments' | 'eventTopics', v: string) =>
    set(key, form[key].includes(v) ? form[key].filter((x) => x !== v) : [...form[key], v]);
  const toggleStream = (s: Stream) => set('streams', form.streams.includes(s) ? form.streams.filter((x) => x !== s) : [...form.streams, s]);

  const text = (key: TextKey, label: string, extra: { inputMode?: 'numeric' | 'decimal'; hint?: string } = {}) => (
    <Field
      label={label}
      name={key}
      value={form[key]}
      onChange={(e) => set(key, e.target.value)}
      error={(errors as Partial<Record<TextKey, string>>)[key]}
      {...extra}
    />
  );
  const number = (key: NumberField, label: string, inputMode: 'numeric' | 'decimal' = 'numeric') => text(key, label, { inputMode });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const found = validate(form);
    setErrors(found);
    if (Object.keys(found).length) {
      setStatus('invalid');
      return;
    }
    setStatus('saving');
    const input = toInput(form, profile?.data);
    try {
      if (profile) {
        await api.updateProfile(profile.id, input);
        setStatus('saved');
        onSaved();
      } else {
        await api.createProfile(input);
        primeCache('profiles', undefined);
        navigate('/profiles', { state: { notice: EDITOR_COPY.created } });
      }
    } catch (err) {
      setStatus(err instanceof ApiError && err.kind === 'invalid' ? 'refused' : 'unreachable');
    }
  };

  const remove = async () => {
    if (!profile) return;
    setDeleteFailed(false);
    try {
      await api.deleteProfile(profile.id);
      primeCache('profiles', undefined);
      navigate('/profiles', { state: { notice: EDITOR_COPY.deleted } });
    } catch {
      setDeleteFailed(true);
    }
  };

  const title = profile ? profile.name : type === 'business' ? EDITOR_COPY.newBusiness : EDITOR_COPY.newPersonal;
  const message =
    status === 'saved'
      ? EDITOR_COPY.saved
      : status === 'invalid'
        ? EDITOR_COPY.checkFields
        : status === 'refused'
          ? EDITOR_COPY.refused
          : status === 'unreachable'
            ? `${COPY.unreachableTitle}. Your changes were not saved; try again.`
            : '';

  return (
    <AppShell path="/profiles" title={title} summary={EDITOR_COPY.summary}>
      <form onSubmit={submit} noValidate aria-label={title} className={styles.form}>
        <Card label={EDITOR_COPY.about} gap={14}>
          <div className={styles.fields}>
            {text('name', EDITOR_COPY.name)}
            {text('location', EDITOR_COPY.location)}
          </div>
          {text('locations', EDITOR_COPY.locations, { hint: EDITOR_COPY.locationsHint })}
          <SwitchRow label={EDITOR_COPY.active} description={EDITOR_COPY.activeHelp} checked={form.active} onChange={(v) => set('active', v)} />
          <ChipGroup label={EDITOR_COPY.streams} error={errors.streams}>
            {STREAMS.map((s) => (
              <FilterChip key={s} stream={s} selected={form.streams.includes(s)} onClick={() => toggleStream(s)} />
            ))}
          </ChipGroup>
        </Card>

        {form.type === 'business' ? (
          <>
            <Card label={EDITOR_COPY.offer} gap={14}>
              <ChipGroup label={EDITOR_COPY.organisationType} hint={EDITOR_COPY.organisationTypeHint}>
                {organisationOptions(form.organisationType).map((o) => (
                  <FilterChip
                    key={o.value}
                    stream="all"
                    label={o.label}
                    selected={form.organisationType === o.value}
                    // One choice; pressing the chosen one again clears the answer.
                    onClick={() => set('organisationType', form.organisationType === o.value ? '' : o.value)}
                  />
                ))}
              </ChipGroup>
              {text('services', EDITOR_COPY.services)}
              {text('sectors', EDITOR_COPY.sectors, { hint: EDITOR_COPY.sectorsHint })}
              <SwitchRow
                label={EDITOR_COPY.provisional}
                description={EDITOR_COPY.provisionalHelp}
                checked={form.provisional}
                onChange={(v) => set('provisional', v)}
              />
              {number('minContractRwf', EDITOR_COPY.minContract)}
            </Card>
            <Card label={EDITOR_COPY.registrations} gap={14}>
              <div className={styles.fields}>
                {text('registrationsHeld', EDITOR_COPY.held)}
                {text('registrationsNotHeld', EDITOR_COPY.notHeld)}
              </div>
            </Card>
            <Card label={EDITOR_COPY.capacity} gap={14}>
              {text('capacityModel', EDITOR_COPY.capacityModel)}
              <div className={styles.fields}>
                {number('trucksInNetwork', EDITOR_COPY.trucks)}
                {number('refrigeratedInNetwork', EDITOR_COPY.refrigerated)}
                {number('ownedTrucks', EDITOR_COPY.owned)}
                {number('tonnageMin', EDITOR_COPY.tonnageMin, 'decimal')}
                {number('tonnageMax', EDITOR_COPY.tonnageMax, 'decimal')}
              </div>
            </Card>
          </>
        ) : (
          <Card label={EDITOR_COPY.interests} gap={14}>
            <ChipGroup label={EDITOR_COPY.instruments}>
              {chipOptions(INSTRUMENTS, form.instruments).map((v) => (
                <FilterChip key={v} stream="all" label={v} selected={form.instruments.includes(v)} onClick={() => toggle('instruments', v)} />
              ))}
            </ChipGroup>
            <div className={styles.fields}>
              {number('ticketMin', EDITOR_COPY.ticketMin)}
              {number('ticketMax', EDITOR_COPY.ticketMax)}
            </div>
            {text('horizon', EDITOR_COPY.horizon, { hint: EDITOR_COPY.horizonHint })}
            <ChipGroup label={EDITOR_COPY.topics}>
              {chipOptions(EVENT_TOPICS, form.eventTopics).map((v) => (
                <FilterChip key={v} stream="all" label={v} selected={form.eventTopics.includes(v)} onClick={() => toggle('eventTopics', v)} />
              ))}
            </ChipGroup>
            <div className={styles.fields}>
              {text('availability', EDITOR_COPY.availability, { hint: EDITOR_COPY.availabilityHint })}
              {number('budgetRwf', EDITOR_COPY.budget)}
            </div>
          </Card>
        )}

        <Card label={EDITOR_COPY.exclusions} gap={14}>
          <div className={styles.fields}>
            {text('excludeOrganisations', EDITOR_COPY.excludeOrganisations)}
            {text('excludeSectors', EDITOR_COPY.excludeSectors)}
            {text('excludeKeywords', EDITOR_COPY.excludeKeywords)}
          </div>
        </Card>

        <div className={styles.actions}>
          <Button type="submit" disabled={status === 'saving'}>
            {profile ? EDITOR_COPY.save : EDITOR_COPY.create}
          </Button>
          <Button variant="secondary" onClick={() => navigate('/profiles')}>
            {EDITOR_COPY.cancel}
          </Button>
        </div>
        <div role="status" className={status === 'saved' ? styles.status : styles.alertStatus}>
          {message}
        </div>
      </form>

      {profile && (
        <Card gap={12} aria-label={EDITOR_COPY.delete}>
          {confirming ? (
            <>
              <div className={styles.status}>{EDITOR_COPY.confirmDelete(profile.name)}</div>
              <div className={styles.actions}>
                <Button onClick={remove}>{EDITOR_COPY.confirm}</Button>
                <Button variant="secondary" onClick={() => setConfirming(false)}>
                  {EDITOR_COPY.keep}
                </Button>
              </div>
              {deleteFailed && (
                <div role="status" className={styles.alertStatus}>
                  {`${COPY.unreachableTitle}. The profile was not deleted; try again.`}
                </div>
              )}
            </>
          ) : (
            <div className={styles.actions}>
              <Button variant="secondary" onClick={() => setConfirming(true)}>
                {EDITOR_COPY.delete}
              </Button>
            </div>
          )}
        </Card>
      )}
    </AppShell>
  );
}
