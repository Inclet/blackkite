import { useId, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router';
import { api } from '../../api/client';
import { sourcesApi } from '../../api/sources';
import { useResource } from '../../api/useResource';
import { Button } from '../../components/Button/Button';
import { Card } from '../../components/Card/Card';
import { FilterChip } from '../../components/FilterChip/FilterChip';
import { TextButton } from '../../components/TextLink/TextLink';
import { FILTER_COPY, FILTER_KEYS, FIXED_CHOICES, filterWord, readFilters, type FilterKey } from '../../lib/feedFilters';
import { ITEM_COPY } from '../items/ItemEditor';
import type { FeedModel } from './model';
import styles from './parts.module.css';

/**
 * Live data only (never on fixtures, so the boards stay as drawn): under the
 * stream chips, "Filters" (a panel of single-choice chip groups, applied at once
 * and kept in the URL), the applied filters as removable chips, "Clear filters",
 * and "Add an item". Design review.
 */
export function FeedTools({ model, className }: { model: FeedModel; className?: string }) {
  if (!model.live) return null;
  return <Tools className={className} />;
}

function Tools({ className }: { className?: string }) {
  const navigate = useNavigate();
  const [search, setSearch] = useSearchParams();
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const filters = readFilters(search);
  const applied = FILTER_KEYS.filter((k) => filters[k]);
  // Shared with the feed (profiles) and the Sources screen (sources), so usually already loaded.
  const profiles = useResource('profiles', (s) => api.profiles(s));
  const sources = useResource(open || filters.source ? 'sources' : null, (s) => sourcesApi.sources(s));
  const names = {
    profiles: Object.fromEntries((profiles.data ?? []).map((p) => [p.id, p.name])),
    sources: Object.fromEntries((sources.data ?? []).map((s) => [s.id, s.name])),
  };

  const set = (key: FilterKey, value: string | null) => {
    const next = new URLSearchParams(search);
    if (value === null) next.delete(key);
    else next.set(key, value);
    setSearch(next, { replace: true });
  };
  const clear = () => {
    const next = new URLSearchParams(search);
    for (const k of FILTER_KEYS) next.delete(k);
    setSearch(next, { replace: true });
  };

  const choices: Record<FilterKey, { anyLabel: string; options: readonly (readonly [string, string])[] }> = {
    profile: { anyLabel: FILTER_COPY.anyProfile, options: (profiles.data ?? []).map((p) => [p.id, p.name] as const) },
    status: { anyLabel: FILTER_COPY.any, options: FIXED_CHOICES.status },
    window: { anyLabel: FILTER_COPY.any, options: FIXED_CHOICES.window },
    fit: { anyLabel: FILTER_COPY.any, options: FIXED_CHOICES.fit },
    source: { anyLabel: FILTER_COPY.anySource, options: (sources.data ?? []).map((s) => [s.id, s.name] as const) },
    verification: { anyLabel: FILTER_COPY.any, options: FIXED_CHOICES.verification },
  };

  return (
    <div className={[styles.toolsWrap, className].filter(Boolean).join(' ')}>
      <div className={styles.tools}>
        <Button variant="secondary" aria-expanded={open} aria-controls={panelId} onClick={() => setOpen((o) => !o)}>
          {applied.length ? FILTER_COPY.buttonCount(applied.length) : FILTER_COPY.button}
        </Button>
        <Button variant="secondary" onClick={() => navigate('/items/new')}>
          {ITEM_COPY.add}
        </Button>
      </div>
      {applied.length > 0 && (
        <div className={styles.applied}>
          <div className={styles.liveText} id={`${panelId}-applied`}>
            {FILTER_COPY.applied}
          </div>
          <div className={styles.progress} role="group" aria-labelledby={`${panelId}-applied`}>
            {applied.map((k) => {
              const word = filterWord(k, filters[k]!, names);
              return (
                <FilterChip
                  key={k}
                  stream="all"
                  action
                  label={`${FILTER_COPY.groups[k]}: ${word}`}
                  aria-label={FILTER_COPY.remove(FILTER_COPY.groups[k], word)}
                  onClick={() => set(k, null)}
                />
              );
            })}
            <TextButton onClick={clear}>{FILTER_COPY.clear}</TextButton>
          </div>
        </div>
      )}
      <div id={panelId} hidden={!open}>
        {open && (
          <Card padding="16px" gap={14} aria-label={FILTER_COPY.panel}>
            {FILTER_KEYS.map((k) => (
              <fieldset key={k} className={styles.filterGroup}>
                <legend className={styles.filterLegend}>{FILTER_COPY.groups[k]}</legend>
                <div className={styles.progress}>
                  <FilterChip stream="all" label={choices[k].anyLabel} selected={!filters[k]} onClick={() => set(k, null)} />
                  {choices[k].options.map(([value, label]) => (
                    <FilterChip key={value} stream="all" label={label} selected={filters[k] === value} onClick={() => set(k, filters[k] === value ? null : value)} />
                  ))}
                </div>
              </fieldset>
            ))}
            {applied.length > 0 && (
              <div>
                <TextButton onClick={clear}>{FILTER_COPY.clear}</TextButton>
              </div>
            )}
          </Card>
        )}
      </div>
    </div>
  );
}
