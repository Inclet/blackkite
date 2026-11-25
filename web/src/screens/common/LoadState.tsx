import { Card } from '../../components/Card/Card';
import { StateCard } from '../../components/StateCard/StateCard';
import type { ApiError } from '../../api/client';
import { COPY } from './copy';

export interface LoadStateProps {
  /** Loading with nothing on screen yet. */
  loading?: boolean;
  /** Loading again with the previous data still shown below. */
  refreshing?: boolean;
  error?: ApiError | null;
  onRetry?: () => void;
  className?: string;
  /** Card padding (the phone uses the board's 22px 24px; the default is the same). */
  padding?: string;
}

/**
 * The circling-kite "checking" card while data loads, or the "source down" card
 * when Blackkite cannot be reached. Both are the Components board's state cards.
 * Renders nothing when there is nothing to say. 401 is handled by the screen (sign-in).
 */
export function LoadState({ loading, refreshing, error, onRetry, className, padding }: LoadStateProps) {
  if (error && error.kind !== 'unauthorized') {
    return (
      <Card className={className} padding={padding} gap={12} aria-label="Status">
        <StateCard
          kind="source-down"
          title={COPY.unreachableTitle}
          body={COPY.unreachableBody}
          action={onRetry ? { label: COPY.tryAgain, onClick: onRetry } : undefined}
        />
      </Card>
    );
  }
  if (loading || refreshing) {
    return (
      <Card className={className} padding={padding} gap={12} aria-label="Status">
        <StateCard
          kind="checking"
          title={loading ? COPY.loadingTitle : COPY.refreshingTitle}
          body={loading ? COPY.loadingBody : COPY.refreshingBody}
        />
      </Card>
    );
  }
  return null;
}
