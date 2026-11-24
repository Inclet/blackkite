/** The four streams. Colours are the design/tokens.css variables (identical to the boards' values). */
export type Stream = 'tender' | 'investment' | 'funding' | 'event';

export const STREAMS: readonly Stream[] = ['tender', 'investment', 'funding', 'event'];

export const STREAM_COLOURS: Record<Stream, { base: string; tint: string; text: string; icon: string }> = {
  tender: { base: 'var(--bk-tender)', tint: 'var(--bk-tender-tint)', text: 'var(--bk-tender-text)', icon: 'var(--bk-tender-icon)' },
  investment: { base: 'var(--bk-investment)', tint: 'var(--bk-investment-tint)', text: 'var(--bk-investment-text)', icon: 'var(--bk-investment)' },
  funding: { base: 'var(--bk-funding)', tint: 'var(--bk-funding-tint)', text: 'var(--bk-funding-text)', icon: 'var(--bk-funding)' },
  event: { base: 'var(--bk-event)', tint: 'var(--bk-event-tint)', text: 'var(--bk-event-text)', icon: 'var(--bk-event)' },
};

/** Singular names, as on tags and icon labels. */
export const STREAM_NAMES: Record<Stream, string> = {
  tender: 'Tender',
  investment: 'Investment',
  funding: 'Funding',
  event: 'Event',
};

/** Plural names, as on filter chips. */
export const STREAM_PLURALS: Record<Stream, string> = {
  tender: 'Tenders',
  investment: 'Investments',
  funding: 'Funding',
  event: 'Events',
};

export function cx(...names: (string | false | null | undefined)[]): string {
  return names.filter(Boolean).join(' ');
}
