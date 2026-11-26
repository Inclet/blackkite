import { useId, useState, type FormEvent, type ReactNode } from 'react';
import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router';
import { ApiError, refusalOf, type FieldError } from '../../api/client';
import {
  COLLECTOR_TYPES,
  SOURCE_KINDS,
  sourcesApi,
  type SourceDetail,
  type CollectorType,
  type CollectorTypeInfo,
  type ConfigField,
  type Preview,
  type RunPage,
  type RunWarning,
  type SourceRun,
  type SourceStatus,
  type Suggestion,
} from '../../api/sources';
import { primeCache, useResource } from '../../api/useResource';
import { Button } from '../../components/Button/Button';
import { Card } from '../../components/Card/Card';
import { Field } from '../../components/Field/Field';
import { FilterChip } from '../../components/FilterChip/FilterChip';
import { SwitchRow } from '../../components/SwitchRow/SwitchRow';
import { Tag } from '../../components/Tag/Tag';
import { TextLink } from '../../components/TextLink/TextLink';
import { httpUrl } from '../../lib/externalUrl';
import { STREAMS, type Stream } from '../../lib/streams';
import { COPY } from '../common/copy';
import { LoadState } from '../common/LoadState';
import { AppShell } from '../shell/AppShell';
import styles from '../sources/Sources.module.css';
import {
  COLLECTOR_WORDS,
  formatDay,
  formatWhen,
  GATE_HELP,
  gateText,
  HISTORY_REASONS,
  sourceGate,
  HEALTH_WORDS,
  KIND_WORDS,
  MOVE_DONE,
  moveLabel,
  RUN_WORDS,
  STATUS_HELP,
  STATUS_MOVES,
  STATUS_WORDS,
} from '../sources/words';
import { adminFailure, AdminOnly, BackToAdmin } from './AdminOnly';
import {
  configValues,
  detailText,
  emptyForm,
  fieldHint,
  fieldKind,
  fieldLabel,
  fieldsFor,
  placeServerErrors,
  switchOn,
  toForm,
  validate,
  validateForTest,
  WHOLE_CONFIG,
  type FormErrors,
  type SourceForm,
} from './sourceForm';

function warningsCount(n: number): string {
  return n === 1 ? '1 warning' : `${n} warnings`;
}

/** A warning's date: ISO 8601 in Kigali time, anything else as the email wrote it. */
function warningDate(date: string): string {
  if (/^\d{4}-\d{2}-\d{2}T/.test(date)) return formatWhen(date);
  if (/^\d{4}-\d{2}-\d{2}$/.test(date)) return formatDay(date);
  return date;
}

/** One run warning in plain words (api RunWarningOut). Unknown kinds show the API's message. */
function warningText(w: RunWarning): string {
  if (w.kind === 'email_no_link') {
    const who = [w.subject ? `"${w.subject}"` : null, w.sender ? `from ${w.sender}` : null].filter(Boolean).join(' ');
    const parts = [who, w.date ? warningDate(w.date) : null].filter(Boolean).join(', ');
    return `Skipped an email with no usable link${parts ? `: ${parts}` : ''}.`;
  }
  const m = (w.message ?? '').trim();
  if (!m) return 'Skipped something without failing.';
  return /[.!?]$/.test(m) ? m : `${m}.`;
}

export const EDITOR_COPY = {
  newTitle: 'New source',
  newSummary: 'Fill in the record, run a test, then save. A new source starts in testing, hidden from members.',
  editSummary: (status: string) => `${status}. Changes are saved when you press Save changes.`,
  back: 'Sources',
  record: 'Record',
  name: 'Name',
  homeUrl: 'Home page',
  publisher: 'Publisher (the organisation behind it)',
  streams: 'Streams it feeds',
  kind: 'Kind',
  schedule: 'Schedule (cron, UTC)',
  scheduleHint: (fallback: string) => `Leave empty for the default${fallback ? `: ${fallback}` : ''}.`,
  rateLimit: 'Seconds between requests',
  rateLimitHint: 'At least 1. Leave empty for the default.',
  accessNote: 'Access note',
  accessNoteHint: 'Robots and terms position, whether a login is needed, what was tested and when.',
  collector: 'Collector',
  collectorType: 'How Blackkite collects from it',
  config: 'Settings for this collector',
  wholeConfig: 'Settings (JSON)',
  wholeConfigHint: 'This collector has no field list, so its settings are edited as JSON.',
  typesFailed: 'We could not load the collector settings. Edit them as JSON, or try again later.',
  activeWarning: 'Changing the collector or its settings sends this source back to testing: it then needs 2 good runs again.',
  testRun: 'Test run',
  testing: 'Running the test…',
  create: 'Save as testing',
  save: 'Save changes',
  saving: 'Saving…',
  checkFields: 'Some answers need a fix. They are marked above.',
  refused: (why: string | null) => `Blackkite did not accept this source.${why ? ` ${why}` : ''}`,
  /** Heading of the list of refusals that are not about a field on this form. */
  otherProblems: 'Also refused:',
  nameTaken: 'Another source already has that name.',
  saved: 'Saved.',
  savedBackToTesting: 'Saved. The settings changed, so it is back in testing.',
  created: 'Saved as testing. It runs on its schedule; its items stay hidden from members until you make it active.',
  unreachableSave: `${COPY.unreachableTitle}. Nothing was saved; try again.`,
  previewLabel: 'Test run results',
  previewNothingSaved: 'Nothing was saved: this run wrote no items and no run history.',
  previewSummary: (total: number, shown: number, requests: number, seconds: number) =>
    `Parsed ${total === 1 ? '1 item' : `${total} items`} with ${requests === 1 ? '1 request' : `${requests} requests`} in ${seconds.toFixed(1)} s.${
      shown < total ? ` Showing the first ${shown}.` : ''
    }`,
  previewFailed: (why: string) => `The test run failed: ${why}`,
  previewEmpty: 'It ran, but found no items. Check the settings.',
  previewRefused: (why: string | null) => `Blackkite did not run the test.${why ? ` ${why}` : ''}`,
  /** 429 without a detail (the API sends its own sentence). */
  previewBusy: 'Another test run is in progress; try again in a minute.',
  tooMany: 'Too many requests just now; try again in a minute.',
  previewUnreachable: `${COPY.unreachableTitle}. The test did not run; try again.`,
  published: (v: string) => `Published ${v}`,
  closes: (v: string) => `Closes ${v}`,
  open: 'Open',
  status: 'Status',
  statusRegion: 'Source status',
  gateRefused: (status: string, gate: string) => `Not changed: it stays ${status.toLowerCase()}. ${gate}`,
  moveRefused: (why: string | null) => `Not changed.${why ? ` ${why.charAt(0).toUpperCase()}${why.slice(1)}${/[.!?]$/.test(why) ? '' : '.'}` : ''}`,
  moveUnreachable: `${COPY.unreachableTitle}. The status did not change; try again.`,
  runs: 'Run history',
  noRuns: 'No runs yet. It runs on its schedule once saved.',
  runLine: (r: SourceRun) =>
    `${r.itemsFound} found · ${r.itemsNew} new${r.itemsFailed ? ` · ${r.itemsFailed} could not be read` : ''}${
      r.warnings?.length ? ` · ${warningsCount(r.warnings.length)}` : ''
    }`,
  errors: 'Error log',
  noErrors: 'No failed runs and no warnings.',
  warning: warningText,
  previewWarnings: 'Skipped without failing:',
  moreRuns: (shown: number, total: number) => `Showing the latest ${shown} of ${total}.`,
  history: 'Status history',
  historyLine: (from: string | null, to: string, reason: string | null) =>
    `${from ? `${from} to ${to}` : `Created as ${to.toLowerCase()}`}${reason && reason !== 'created' ? `, because ${HISTORY_REASONS[reason] ?? reason}` : ''}`,
  notBuilt: 'This collector is not built yet: its test runs and scheduled runs fail until it is. The settings below are the ones the spec lists.',
  notFound: 'We could not find that source.',
  fromSuggestion: 'From a member’s suggestion',
} as const;

/** /admin/sources/new (also ?suggestion=<id>) and /admin/sources/:id. Design review. */
export function SourceEditor() {
  const { id } = useParams();
  const path = id ? `/admin/sources/${id}` : '/admin/sources/new';
  return (
    <AdminOnly path={path} title={id ? 'Source' : EDITOR_COPY.newTitle}>
      {id ? <Existing id={id} /> : <New />}
    </AdminOnly>
  );
}

function New() {
  const [search] = useSearchParams();
  const suggestionId = search.get('suggestion');
  const types = useResource('collector-types', (s) => sourcesApi.collectorTypes(s));
  const accepted = useResource(suggestionId ? 'admin-suggestions-accepted' : null, (s) => sourcesApi.adminSuggestions('accepted', s));
  const failed = adminFailure('/admin/sources/new', types.error, accepted.error);
  if (failed) return failed;
  // Wait for the collector types: an editor drawn before they arrive would start the
  // config as JSON, and a type chosen in that moment would keep the JSON shape.
  if (types.loading || (suggestionId && !accepted.data)) {
    return (
      <AppShell path="/admin/sources/new" title={EDITOR_COPY.newTitle}>
        <LoadState loading={types.loading || accepted.loading} error={accepted.error} onRetry={accepted.reload} />
      </AppShell>
    );
  }
  const suggestion = suggestionId ? (accepted.data?.find((s) => s.id === suggestionId && !s.sourceId) ?? null) : null;
  return <Editor key={suggestion?.id ?? 'new'} source={null} suggestion={suggestion} types={types.data} typesFailed={!!types.error} onSaved={() => {}} />;
}

function Existing({ id }: { id: string }) {
  const source = useResource(`admin-source-${id}`, (s) => sourcesApi.adminSource(id, s));
  const types = useResource('collector-types', (s) => sourcesApi.collectorTypes(s));
  const runs = useResource(`admin-runs-${id}`, (s) => sourcesApi.runs(id, {}, s));
  const errorLog = useResource(`admin-run-errors-${id}`, (s) => sourcesApi.runs(id, { problems: true }, s));
  const path = `/admin/sources/${id}`;
  const failed = adminFailure(path, source.error, types.error, runs.error);
  if (failed) return failed;
  if (!source.data || types.loading) {
    return (
      <AppShell path={path} title="Source">
        <BackToAdmin to="/admin/sources" label={EDITOR_COPY.back} />
        {source.error?.kind === 'not-found' ? (
          <Card aria-label="Not found">
            <div className={styles.status}>{EDITOR_COPY.notFound}</div>
          </Card>
        ) : (
          <LoadState loading={source.loading || types.loading} error={source.error} onRetry={source.reload} />
        )}
      </AppShell>
    );
  }
  return (
    <Editor
      key={`${source.data.id}-${types.data ? 'typed' : 'raw'}`}
      source={source.data}
      suggestion={null}
      types={types.data}
      typesFailed={!!types.error}
      runs={runs.data}
      errorLog={errorLog.data}
      onSaved={(s) => {
        source.setData(() => s);
        primeCache('admin-sources', undefined);
      }}
    />
  );
}

function ChipGroup({ label, error, children }: { label: string; error?: string; children: ReactNode }) {
  const errorId = useId();
  return (
    <fieldset className={styles.group} aria-describedby={error ? errorId : undefined}>
      <legend className={styles.groupLabel}>{label}</legend>
      <div className={styles.chips}>{children}</div>
      {error && (
        <div id={errorId} className={styles.error}>
          {error}
        </div>
      )}
    </fieldset>
  );
}

type SaveStatus = { kind: 'idle' | 'saving' | 'saved' | 'invalid' | 'refused' | 'unreachable'; text: string };
type TestState = { kind: 'idle' } | { kind: 'running' } | { kind: 'done'; preview: Preview } | { kind: 'failed'; text: string };

interface EditorProps {
  source: SourceDetail | null;
  suggestion: Suggestion | null;
  types: CollectorTypeInfo[] | undefined;
  typesFailed: boolean;
  runs?: RunPage;
  errorLog?: RunPage;
  onSaved: (s: SourceDetail) => void;
}

function Editor({ source, suggestion, types, typesFailed, runs, errorLog, onSaved }: EditorProps) {
  const navigate = useNavigate();
  const { state } = useLocation();
  const [form, setForm] = useState<SourceForm>(() => {
    if (source) return toForm(source, types);
    return { ...emptyForm(), homeUrl: suggestion?.url ?? '' };
  });
  const [errors, setErrors] = useState<FormErrors>({});
  const [save, setSave] = useState<SaveStatus>(() => ({ kind: 'idle', text: (state as { notice?: string } | null)?.notice ?? '' }));
  const [test, setTest] = useState<TestState>({ kind: 'idle' });
  /** Server refusals that are not about a field on this form, as sentences. */
  const [unplaced, setUnplaced] = useState<string[]>([]);

  const fields = fieldsFor(types, form.collectorType);
  // Keys the field list does not describe survive an edit, but only within the same collector type.
  const base = source && source.collectorType === form.collectorType ? source.config : undefined;

  const set = <K extends keyof SourceForm>(key: K, value: SourceForm[K]) => {
    setForm((f) => ({ ...f, [key]: value }));
    if (save.kind === 'saved') setSave({ kind: 'idle', text: '' });
  };
  const setConfig = (name: string, value: string | boolean) => set('config', { ...form.config, [name]: value });
  const chooseType = (t: CollectorType) => {
    if (t === form.collectorType) return;
    const keep = source && source.collectorType === t ? source.config : {};
    setForm((f) => ({ ...f, collectorType: t, config: configValues(fieldsFor(types, t), keep) }));
  };
  /** Show the server's field errors next to their fields (client checks for the rest stay as found). */
  const showServerErrors = (found: FieldError[], clientErrors: FormErrors) => {
    const { placed, unplaced: rest } = placeServerErrors(found, fields);
    setErrors({ ...clientErrors, ...placed, config: { ...clientErrors.config, ...placed.config } });
    setUnplaced(rest);
  };
  /** A new action replaces the last one's status line ("Saved as testing…" must not sit next to a refusal). */
  const startAction = () => {
    if (save.kind !== 'saving') setSave({ kind: 'idle', text: '' });
    setUnplaced([]);
  };
  const toggleStream = (s: Stream) => set('streams', form.streams.includes(s) ? form.streams.filter((x) => x !== s) : [...form.streams, s]);

  const runTest = async () => {
    startAction();
    const checked = validateForTest(form, fields, base);
    setErrors(checked.errors);
    if (!checked.ok || !form.collectorType) {
      setTest({ kind: 'failed', text: EDITOR_COPY.checkFields });
      return;
    }
    setTest({ kind: 'running' });
    try {
      const preview = await sourcesApi.testRun({
        collectorType: form.collectorType,
        config: checked.config,
        homeUrl: form.homeUrl.trim() || null,
        streams: form.streams.length ? form.streams : ['tender'],
        rateLimit: form.rateLimit.trim() ? Number(form.rateLimit) : null,
      });
      if (preview.errors?.length) showServerErrors(preview.errors, checked.errors);
      setTest({ kind: 'done', preview });
    } catch (err) {
      if (err instanceof ApiError && err.kind === 'invalid') {
        const refusal = refusalOf(err);
        showServerErrors(refusal.errors, checked.errors);
        setTest({ kind: 'failed', text: EDITOR_COPY.previewRefused(refusal.detail ?? detailText(err.detail)) });
      } else if (err instanceof ApiError && err.kind === 'too-many') {
        setTest({ kind: 'failed', text: refusalOf(err).detail ?? EDITOR_COPY.previewBusy });
      } else {
        setTest({ kind: 'failed', text: EDITOR_COPY.previewUnreachable });
      }
    }
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setUnplaced([]);
    const { errors: found, body } = validate(form, fields, base);
    setErrors(found);
    if (!body) {
      setSave({ kind: 'invalid', text: EDITOR_COPY.checkFields });
      return;
    }
    setSave({ kind: 'saving', text: EDITOR_COPY.saving });
    try {
      if (source) {
        const saved = await sourcesApi.updateSource(source.id, body);
        onSaved(saved);
        setSave({ kind: 'saved', text: source.status === 'active' && saved.status === 'testing' ? EDITOR_COPY.savedBackToTesting : EDITOR_COPY.saved });
      } else {
        const created = await sourcesApi.createSource(suggestion ? { ...body, suggestionId: suggestion.id } : body);
        primeCache('admin-sources', undefined);
        primeCache('admin-suggestions-accepted', undefined);
        navigate(`/admin/sources/${encodeURIComponent(created.id)}`, { state: { notice: EDITOR_COPY.created } });
      }
    } catch (err) {
      if (err instanceof ApiError && (err.kind === 'conflict' || err.kind === 'invalid')) {
        const refusal = refusalOf(err);
        showServerErrors(refusal.errors, found);
        setSave({
          kind: 'refused',
          text: err.kind === 'conflict' ? EDITOR_COPY.nameTaken : EDITOR_COPY.refused(refusal.detail ?? detailText(err.detail)),
        });
      } else if (err instanceof ApiError && err.kind === 'too-many') {
        setSave({ kind: 'refused', text: refusalOf(err).detail ?? EDITOR_COPY.tooMany });
      } else setSave({ kind: 'unreachable', text: EDITOR_COPY.unreachableSave });
    }
  };

  const path = source ? `/admin/sources/${source.id}` : '/admin/sources/new';
  const title = source ? source.name : EDITOR_COPY.newTitle;
  const summary = source ? EDITOR_COPY.editSummary(STATUS_WORDS[source.status]) : EDITOR_COPY.newSummary;
  const typeLabel = (t: CollectorType) => types?.find((x) => x.type === t)?.label ?? COLLECTOR_WORDS[t];

  return (
    <AppShell path={path} title={title} summary={summary}>
      <BackToAdmin to="/admin/sources" label={EDITOR_COPY.back} />
      {suggestion && (
        <Card label={EDITOR_COPY.fromSuggestion} gap={6} aria-label={EDITOR_COPY.fromSuggestion}>
          <span className={styles.rowTitle}>{suggestion.url}</span>
          {suggestion.note && <div className={styles.note}>{suggestion.note}</div>}
        </Card>
      )}
      {source && <StatusCard source={source} onChanged={onSaved} onStart={startAction} />}

      <form onSubmit={submit} noValidate aria-label={title} className={styles.form} style={{ gap: 'inherit' }}>
        <Card label={EDITOR_COPY.record} gap={14}>
          <div className={styles.fields}>
            <Field label={EDITOR_COPY.name} name="name" value={form.name} error={errors.name} onChange={(e) => set('name', e.target.value)} />
            <Field
              label={EDITOR_COPY.homeUrl}
              name="homeUrl"
              type="url"
              inputMode="url"
              value={form.homeUrl}
              error={errors.homeUrl}
              onChange={(e) => set('homeUrl', e.target.value)}
            />
          </div>
          <Field label={EDITOR_COPY.publisher} name="publisher" value={form.publisher} error={errors.publisher} onChange={(e) => set('publisher', e.target.value)} />
          <ChipGroup label={EDITOR_COPY.streams} error={errors.streams}>
            {STREAMS.map((s) => (
              <FilterChip key={s} stream={s} selected={form.streams.includes(s)} onClick={() => toggleStream(s)} />
            ))}
          </ChipGroup>
          <ChipGroup label={EDITOR_COPY.kind} error={errors.kind}>
            {SOURCE_KINDS.map((k) => (
              <FilterChip key={k} stream="all" label={KIND_WORDS[k]} selected={form.kind === k} onClick={() => set('kind', k)} />
            ))}
          </ChipGroup>
          <div className={styles.fields}>
            <Field
              label={EDITOR_COPY.schedule}
              name="schedule"
              value={form.schedule}
              hint={EDITOR_COPY.scheduleHint(source?.effectiveSchedule && !source.schedule ? source.effectiveSchedule : '')}
              error={errors.schedule}
              onChange={(e) => set('schedule', e.target.value)}
            />
            <Field
              label={EDITOR_COPY.rateLimit}
              name="rateLimit"
              inputMode="decimal"
              value={form.rateLimit}
              hint={EDITOR_COPY.rateLimitHint}
              error={errors.rateLimit}
              onChange={(e) => set('rateLimit', e.target.value)}
            />
          </div>
          <Field
            label={EDITOR_COPY.accessNote}
            name="accessNote"
            value={form.accessNote}
            hint={EDITOR_COPY.accessNoteHint}
            maxLength={5000}
            error={errors.accessNote}
            onChange={(e) => set('accessNote', e.target.value)}
          />
        </Card>

        <Card label={EDITOR_COPY.collector} gap={14}>
          <ChipGroup label={EDITOR_COPY.collectorType} error={errors.collectorType}>
            {COLLECTOR_TYPES.map((t) => (
              <FilterChip key={t} stream="all" label={typeLabel(t)} selected={form.collectorType === t} onClick={() => chooseType(t)} />
            ))}
          </ChipGroup>
          {source?.status === 'active' && <div className={styles.status}>{EDITOR_COPY.activeWarning}</div>}
          {typesFailed && <div className={styles.alertStatus}>{EDITOR_COPY.typesFailed}</div>}
          {types?.find((t) => t.type === form.collectorType)?.implemented === false && <div className={styles.status}>{EDITOR_COPY.notBuilt}</div>}
          {form.collectorType && (
            <ConfigFields fields={fields} values={form.config} errors={errors.config ?? {}} onChange={setConfig} />
          )}
        </Card>

        <div className={styles.actions}>
          <Button variant="secondary" onClick={() => void runTest()} disabled={test.kind === 'running'}>
            {EDITOR_COPY.testRun}
          </Button>
          <Button type="submit" disabled={save.kind === 'saving'}>
            {source ? EDITOR_COPY.save : EDITOR_COPY.create}
          </Button>
        </div>
        <div role="status" className={save.kind === 'saved' || save.kind === 'saving' || save.kind === 'idle' ? styles.status : styles.alertStatus}>
          {save.text}
        </div>
        {unplaced.length > 0 && (
          <div className={styles.alertStatus}>
            <div>{EDITOR_COPY.otherProblems}</div>
            {unplaced.map((t, i) => (
              <div key={i}>{t}</div>
            ))}
          </div>
        )}
      </form>

      <TestResult test={test} />
      {source && <Runs runs={runs} errorLog={errorLog} />}
      {source && source.statusHistory?.length > 0 && <History source={source} />}
    </AppShell>
  );
}

function ConfigFields({
  fields,
  values,
  errors,
  onChange,
}: {
  fields: ConfigField[] | null;
  values: Record<string, string | boolean>;
  errors: Record<string, string>;
  onChange: (name: string, value: string | boolean) => void;
}) {
  if (!fields) {
    return (
      <Field
        label={EDITOR_COPY.wholeConfig}
        name={WHOLE_CONFIG}
        value={String(values[WHOLE_CONFIG] ?? '')}
        hint={EDITOR_COPY.wholeConfigHint}
        error={errors[WHOLE_CONFIG]}
        onChange={(e) => onChange(WHOLE_CONFIG, e.target.value)}
      />
    );
  }
  return (
    <fieldset className={styles.group} style={{ gap: 14 }}>
      <legend className={styles.groupLabel}>{EDITOR_COPY.config}</legend>
      {fields.map((f) => {
        const kind = fieldKind(f.kind);
        const label = `${fieldLabel(f)}${f.required ? '' : ' (optional)'}`;
        if (kind === 'boolean') {
          return (
            <SwitchRow key={f.name} label={label} description={f.help ?? undefined} checked={switchOn(f, values)} onChange={(v) => onChange(f.name, v)} />
          );
        }
        const hint = fieldHint(f);
        if (kind === 'choice' && f.options?.length) {
          return (
            <ChipGroup key={f.name} label={label} error={errors[f.name]}>
              {f.options.map((o) => (
                <FilterChip
                  key={o}
                  stream="all"
                  label={o}
                  selected={values[f.name] === o}
                  onClick={() => onChange(f.name, values[f.name] === o && !f.required ? '' : o)}
                />
              ))}
            </ChipGroup>
          );
        }
        return (
          <Field
            key={f.name}
            label={label}
            name={f.name}
            type={kind === 'url' ? 'url' : 'text'}
            inputMode={kind === 'integer' ? 'numeric' : kind === 'number' ? 'decimal' : kind === 'url' ? 'url' : undefined}
            value={String(values[f.name] ?? '')}
            hint={hint}
            error={errors[f.name]}
            onChange={(e) => onChange(f.name, e.target.value)}
          />
        );
      })}
    </fieldset>
  );
}

function TestResult({ test }: { test: TestState }) {
  if (test.kind === 'idle') return <div role="status" className={styles.status} />;
  if (test.kind === 'running') {
    return (
      <div role="status" className={styles.status}>
        {EDITOR_COPY.testing}
      </div>
    );
  }
  if (test.kind === 'failed') {
    return (
      <div role="status" className={styles.alertStatus}>
        {test.text}
      </div>
    );
  }
  const p = test.preview;
  return (
    <Card label={EDITOR_COPY.previewLabel} padding="22px 24px 12px" gap={6} aria-label={EDITOR_COPY.previewLabel}>
      <div role="status" className={styles.form} style={{ gap: 4 }}>
        {!p.ok && p.error && <div className={styles.alertStatus}>{EDITOR_COPY.previewFailed(p.error)}</div>}
        {p.ok && p.items.length === 0 && <div className={styles.alertStatus}>{EDITOR_COPY.previewEmpty}</div>}
        <div className={styles.status}>{EDITOR_COPY.previewSummary(p.totalParsed, p.items.length, p.requestsMade, p.elapsedSeconds)}</div>
        <div className={styles.status}>{EDITOR_COPY.previewNothingSaved}</div>
        {p.warnings.length > 0 && (
          <>
            <div className={styles.status}>{EDITOR_COPY.previewWarnings}</div>
            {p.warnings.map((w, i) => (
              <div key={i} className={styles.note}>
                {EDITOR_COPY.warning(w)}
              </div>
            ))}
          </>
        )}
      </div>
      {p.items.length > 0 && (
        <div className={styles.rows}>
          {p.items.map((item, i) => {
            const href = httpUrl(item.url);
            const dates = [item.listedPublished && EDITOR_COPY.published(item.listedPublished), item.listedDeadline && EDITOR_COPY.closes(item.listedDeadline)]
              .filter(Boolean)
              .join(' · ');
            return (
              <div key={`${item.url}-${i}`} className={styles.row}>
                <div className={styles.rowText}>
                  <span className={styles.rowTitle}>{item.title}</span>
                  {item.organisation && <span className={styles.meta}>{item.organisation}</span>}
                  {dates && <span className={styles.meta}>{dates}</span>}
                  {item.snippet && <span className={styles.note}>{item.snippet}</span>}
                  <span className={styles.meta}>{item.url}</span>
                </div>
                {href && (
                  <TextLink href={href} target="_blank" rel="noopener noreferrer" aria-label={`${EDITOR_COPY.open} ${item.title}`}>
                    {EDITOR_COPY.open}
                  </TextLink>
                )}
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}

function StatusCard({ source, onChanged, onStart }: { source: SourceDetail; onChanged: (s: SourceDetail) => void; onStart: () => void }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; alert: boolean } | null>(null);
  /** The server's gate numbers from the last refused promotion (409 goodRuns/needed), newer than the loaded source's. */
  const [refusedGate, setRefusedGate] = useState<{ goodRuns: number; needed: number } | null>(null);
  const gate = refusedGate ? gateText(refusedGate.goodRuns, refusedGate.needed) : sourceGate(source);
  const moves = STATUS_MOVES[source.status] ?? [];
  const canPromote = moves.includes('active');

  const move = async (to: SourceStatus) => {
    setBusy(true);
    setMessage(null);
    onStart();
    try {
      const s = await sourcesApi.setStatus(source.id, to);
      setRefusedGate(null);
      onChanged(s);
      setMessage({ text: MOVE_DONE[s.status] ?? '', alert: false });
    } catch (err) {
      if (err instanceof ApiError && err.kind === 'conflict') {
        const numbers = gateNumbers(err.body);
        const detail = refusalOf(err).detail ?? detailText(err.detail);
        if (numbers) {
          setRefusedGate(numbers);
          setMessage({ text: EDITOR_COPY.gateRefused(STATUS_WORDS[source.status], gateText(numbers.goodRuns, numbers.needed)), alert: true });
        } else {
          // A status-graph refusal (or an older answer without the numbers): the server's own sentence.
          setMessage({ text: EDITOR_COPY.moveRefused(detail), alert: true });
        }
      } else {
        setMessage({ text: EDITOR_COPY.moveUnreachable, alert: true });
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card label={EDITOR_COPY.status} gap={10} aria-label={EDITOR_COPY.statusRegion}>
      <div className={styles.side}>
        <Tag kind="profile">{STATUS_WORDS[source.status]}</Tag>
        <Tag kind="profile">{`Health: ${HEALTH_WORDS[source.health]}`}</Tag>
      </div>
      <div className={styles.status}>{STATUS_HELP[source.status]}</div>
      {canPromote && (
        <div className={styles.status}>
          {gate} {GATE_HELP}
        </div>
      )}
      <div className={styles.actions}>
        {moves.map((to) => (
          <Button key={to} variant={to === 'active' ? 'primary' : 'secondary'} disabled={busy} onClick={() => void move(to)}>
            {moveLabel(source.status, to)}
          </Button>
        ))}
      </div>
      <div role="status" className={message?.alert ? styles.alertStatus : styles.status}>
        {message?.text ?? ''}
      </div>
    </Card>
  );
}

/** The promotion refusal's numbers (409 {detail, errors, goodRuns, needed}), when sent. */
function gateNumbers(body: unknown): { goodRuns: number; needed: number } | null {
  if (body === null || typeof body !== 'object') return null;
  const { goodRuns, needed } = body as { goodRuns?: unknown; needed?: unknown };
  return typeof goodRuns === 'number' && typeof needed === 'number' ? { goodRuns, needed } : null;
}

function Runs({ runs, errorLog }: { runs: RunPage | undefined; errorLog: RunPage | undefined }) {
  if (!runs) return null;
  return (
    <>
      <Card label={EDITOR_COPY.runs} padding="22px 24px 12px" gap={4} aria-label={EDITOR_COPY.runs}>
        {runs.items.length === 0 ? (
          <div className={styles.status} style={{ paddingBottom: 10 }}>
            {EDITOR_COPY.noRuns}
          </div>
        ) : (
          <div className={styles.rows}>
            {runs.items.map((r) => (
              <div key={r.id} className={styles.row}>
                <div className={styles.rowText}>
                  <span className={styles.rowTitle}>{formatWhen(r.startedAt)}</span>
                  <span className={styles.meta}>{EDITOR_COPY.runLine(r)}</span>
                </div>
                <Tag kind="profile">{RUN_WORDS[r.status] ?? r.status}</Tag>
              </div>
            ))}
          </div>
        )}
        {runs.total > runs.items.length && (
          <div className={styles.status} style={{ paddingBottom: 10 }}>
            {EDITOR_COPY.moreRuns(runs.items.length, runs.total)}
          </div>
        )}
      </Card>
      {errorLog && (
        <Card label={EDITOR_COPY.errors} padding="22px 24px 12px" gap={4} aria-label={EDITOR_COPY.errors}>
          {errorLog.items.length === 0 ? (
            <div className={styles.status} style={{ paddingBottom: 10 }}>
              {EDITOR_COPY.noErrors}
            </div>
          ) : (
            <div className={styles.rows}>
              {errorLog.items.map((r) => (
                <div key={r.id} className={styles.stackRow}>
                  <span className={styles.rowTitle}>{formatWhen(r.startedAt)}</span>
                  {(r.status === 'failed' || r.error) && <span className={styles.note}>{r.error ?? RUN_WORDS.failed}</span>}
                  {r.warnings.map((w, i) => (
                    <span key={i} className={styles.note}>
                      {EDITOR_COPY.warning(w)}
                    </span>
                  ))}
                </div>
              ))}
            </div>
          )}
          {errorLog.total > errorLog.items.length && (
            <div className={styles.status} style={{ paddingBottom: 10 }}>
              {EDITOR_COPY.moreRuns(errorLog.items.length, errorLog.total)}
            </div>
          )}
        </Card>
      )}
    </>
  );
}

function History({ source }: { source: SourceDetail }) {
  return (
    <Card label={EDITOR_COPY.history} padding="22px 24px 12px" gap={4} aria-label={EDITOR_COPY.history}>
      <div className={styles.rows}>
        {source.statusHistory.map((h, i) => (
          <div key={`${h.at}-${i}`} className={styles.row}>
            <div className={styles.rowText}>
              <span className={styles.rowTitle}>{formatWhen(h.at)}</span>
              <span className={styles.meta}>{EDITOR_COPY.historyLine(h.oldStatus ? STATUS_WORDS[h.oldStatus] : null, STATUS_WORDS[h.newStatus] ?? h.newStatus, h.reason)}</span>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}
