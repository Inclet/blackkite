import { useId, useState, type ReactNode } from 'react';
import type { OwnedDetail } from '../../api/m4';
import { Tag } from '../../components/Tag/Tag';
import { TextLink } from '../../components/TextLink/TextLink';
import { changeSentence, detailLines, formatWhen } from '../../lib/detailWords';
import { httpUrl } from '../../lib/externalUrl';
import styles from './parts.module.css';

/** Not on any board (design review). */
export const SECTIONS_COPY = {
  details: 'Details',
  sources: 'Sources',
  documents: 'Documents',
  history: 'History',
  fromNotice: 'from the notice:',
  noDetails: 'Nothing was read from the notice yet.',
  original: 'Original',
  seen: (first: string, last: string) => `First seen ${first} · last seen ${last}`,
  noOriginal: 'None of these is the original notice.',
  noSourcesOwn: 'No source carries this item. You added it yourself.',
  noSourcesManual: 'A member added this item; no collected source carries it.',
  noSources: 'No sources to show.',
  documentsNote: 'Kept for reference. Open the original to read them.',
  noDocuments: 'No documents.',
  noHistory: 'No changes since Blackkite first saw it.',
  open: (name: string) => `Open ${name} (opens in a new tab)`,
} as const;

/**
 * Live data only, under the note: what was read from the notice with the passages
 * behind it, every source that carried it, documents by name, and the change
 * history in plain words (spec 4.4, 8). On the phone each section starts closed,
 * behind a real button (aria-expanded).
 */
/** Why the Sources section is empty: the owner added it, another member did, or nothing to say. */
export function noSourcesText(detail: OwnedDetail['detail']): string {
  if (detail.ownItem) return SECTIONS_COPY.noSourcesOwn;
  if (detail.isManual) return SECTIONS_COPY.noSourcesManual;
  return SECTIONS_COPY.noSources;
}

export function DetailSections({ detail, collapsible, headingLevel }: { detail: OwnedDetail['detail']; collapsible: boolean; headingLevel: 2 | 3 }) {
  const lines = detailLines(detail.fields ?? []);
  const sources = detail.sources ?? [];
  const documents = detail.documents ?? [];
  const changes = [...(detail.changes ?? [])].sort((a, b) => b.at.localeCompare(a.at));
  return (
    <div className={styles.sections}>
      <Section title={SECTIONS_COPY.details} collapsible={collapsible} level={headingLevel}>
        {lines.length === 0 ? (
          <p className={styles.liveText}>{SECTIONS_COPY.noDetails}</p>
        ) : (
          <dl className={styles.fields}>
            {lines.map((l) => (
              <div key={l.name} className={styles.fieldRow}>
                <dt className={styles.fieldLabel}>{l.label}</dt>
                {l.values.map((v, i) => (
                  <dd key={i} className={styles.fieldValue}>
                    <span>{v.text}</span>
                    {v.quotes.map((q, j) => (
                      <span key={j} className={styles.quote}>
                        {' — '}
                        {SECTIONS_COPY.fromNotice} <q>{q}</q>
                      </span>
                    ))}
                  </dd>
                ))}
              </div>
            ))}
          </dl>
        )}
      </Section>

      <Section title={SECTIONS_COPY.sources} collapsible={collapsible} level={headingLevel}>
        {sources.length === 0 ? (
          <p className={styles.liveText}>{noSourcesText(detail)}</p>
        ) : (
          <>
            <ul className={styles.sectionList}>
              {sources.map((s, i) => {
                const url = httpUrl(s.url);
                return (
                  <li key={`${s.name}-${i}`} className={styles.sourceRow}>
                    <span className={styles.sourceName}>
                      {url ? (
                        <TextLink href={url} target="_blank" rel="noopener noreferrer" aria-label={SECTIONS_COPY.open(s.name)} className={styles.sourceLink}>
                          {s.name}
                        </TextLink>
                      ) : (
                        <span>{s.name}</span>
                      )}
                      {s.isOriginal && <Tag kind="profile">{SECTIONS_COPY.original}</Tag>}
                    </span>
                    <span className={styles.liveText}>{SECTIONS_COPY.seen(formatWhen(s.firstSeen.slice(0, 10)), formatWhen(s.lastSeen.slice(0, 10)))}</span>
                  </li>
                );
              })}
            </ul>
            {!sources.some((s) => s.isOriginal) && <p className={styles.liveText}>{SECTIONS_COPY.noOriginal}</p>}
          </>
        )}
      </Section>

      <Section title={SECTIONS_COPY.documents} collapsible={collapsible} level={headingLevel}>
        {documents.length === 0 ? (
          <p className={styles.liveText}>{SECTIONS_COPY.noDocuments}</p>
        ) : (
          <>
            <ul className={styles.sectionList}>
              {documents.map((d, i) => (
                <li key={`${d.name}-${i}`} className={styles.docName}>
                  {d.name}
                </li>
              ))}
            </ul>
            <p className={styles.liveText}>{SECTIONS_COPY.documentsNote}</p>
          </>
        )}
      </Section>

      <Section title={SECTIONS_COPY.history} collapsible={collapsible} level={headingLevel}>
        {changes.length === 0 ? (
          <p className={styles.liveText}>{SECTIONS_COPY.noHistory}</p>
        ) : (
          <ul className={styles.sectionList}>
            {changes.map((c, i) => (
              <li key={`${c.field}-${c.at}-${i}`} className={styles.historyRow}>
                {changeSentence(c)}
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  );
}

function Section({ title, collapsible, level, children }: { title: string; collapsible: boolean; level: 2 | 3; children: ReactNode }) {
  const [open, setOpen] = useState(!collapsible);
  const id = useId();
  const H = level === 2 ? 'h2' : 'h3';
  return (
    <section className={styles.section} aria-labelledby={`${id}-h`}>
      <H id={`${id}-h`} className={styles.sectionTitle}>
        {collapsible ? (
          <button type="button" className={styles.sectionToggle} aria-expanded={open} aria-controls={`${id}-body`} onClick={() => setOpen((o) => !o)}>
            {title}
            <span className={styles.sectionHint}>{open ? 'Hide' : 'Show'}</span>
          </button>
        ) : (
          title
        )}
      </H>
      <div id={`${id}-body`} hidden={!open} className={styles.sectionBody}>
        {children}
      </div>
    </section>
  );
}
