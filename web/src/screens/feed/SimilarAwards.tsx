import type { DetailBenchmark } from '../../api/m5';
import { TextLink } from '../../components/TextLink/TextLink';
import { detailBenchmarkSentence } from '../../lib/benchmarkWords';
import { useAppLink } from '../../lib/useAppLink';
import styles from './parts.module.css';

/** Not on any board (design review). */
export const SIMILAR_COPY = {
  heading: 'Similar awarded contracts',
} as const;

/**
 * Live tender detail only (pane and phone page): what similar contracts were
 * awarded for, when `detail.benchmark` is sent (its category has at least 3
 * awards; contract section 6). The sentence links to the category's awards.
 */
export function SimilarAwards({ stream, benchmark }: { stream: string; benchmark: DetailBenchmark | null | undefined }) {
  const link = useAppLink();
  const sentence = stream === 'tender' ? detailBenchmarkSentence(benchmark) : null;
  if (!benchmark || !sentence) return null;
  return (
    <>
      <div className={styles.liveLabel}>{SIMILAR_COPY.heading}</div>
      <p className={styles.similar}>
        <TextLink spacing="stacked" {...link(`/benchmarks/${encodeURIComponent(benchmark.category)}`)}>
          {sentence}
        </TextLink>
      </p>
    </>
  );
}
